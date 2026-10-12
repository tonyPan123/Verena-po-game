"""Search mined template abstractions with configurable depth and phase limits.

Every candidate includes the projected initial belief. Candidate failure or
timeout triggers further search; only forward-planning failure proves
unrealizability. Acceptance requires successful native strategy extraction.
"""
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from z3 import *
from z3.z3util import get_vars


def smt(formula):
    solver = Solver()
    solver.add(formula)
    return solver.to_smt2()


def lift_bounds(formulas, memory):
    parameters = {}
    def visit(expr):
        if is_rational_value(expr):
            value = expr.as_fraction()
            if abs(value) > 1:
                key = str(abs(value))
                if key not in parameters:
                    parameters[key] = FreshReal('bound')
                return parameters[key] if value > 0 else -parameters[key]
        if expr.num_args() == 0:
            return expr
        if is_mul(expr) or expr.decl().kind() in (Z3_OP_DIV, Z3_OP_IDIV):
            return expr.decl()(*[c if is_rational_value(c) else visit(c) for c in expr.children()])
        return expr.decl()(*[visit(c) for c in expr.children()])
    result = [visit(simplify(t)) for t in formulas]
    return result, list(memory) + list(parameters.values())


def pack_memory(formulas, memory):
    result, maximum = [], 0
    for formula in formulas:
        used = {v.get_id() for v in get_vars(formula)}
        local = [v for v in memory if v.get_id() in used]
        maximum = max(maximum, len(local))
        result.append(substitute(formula, *[(v, Real(f'm{i+1}')) for i, v in enumerate(local)]))
    return result, [Real(f'm{i+1}') for i in range(maximum)]


def features(formula, memory):
    """Prefer few parameters and no concrete sampled bounds; mix shape families."""
    # SMT-LIB reloads rational literals as division expressions. Normalize
    # before classifying them so numeric bounds are not mistaken for divisors.
    formula = simplify(formula)
    branches, bounds, nodes = 0, set(), 0
    def visit(expr, coefficient=False):
        nonlocal branches, nodes
        nodes += 1
        branches += int(is_or(expr))
        if is_rational_value(expr) and not coefficient and abs(expr.as_fraction()) > 1:
            bounds.add(abs(expr.as_fraction()))
        for child in expr.children():
            visit(child, is_mul(expr) or expr.decl().kind() in (Z3_OP_DIV, Z3_OP_IDIV))
    visit(formula)
    used = {v.get_id() for v in get_vars(formula)}
    return (len(bounds), sum(v.get_id() in used for v in memory), nodes), bool(branches)


def interval_candidates(formulas, memory):
    """Recombine mined lower/upper bounds and a point relation.

This closes a small gap between runs where the miner emits a bounded interval
and runs where it emits its bounds in separate branches. No game field names,
constants, or stored template IDs are used.
    """
    memory_ids = {v.get_id() for v in memory}
    atoms = {}
    def collect(expr):
        if is_and(expr) or is_or(expr):
            for child in expr.children():
                collect(child)
        elif expr.decl().kind() in (Z3_OP_LT, Z3_OP_LE, Z3_OP_GT, Z3_OP_GE, Z3_OP_EQ):
            atoms[expr.sexpr()] = expr
    for formula in formulas:
        collect(formula)
    bounds, points = {}, []
    for atom in atoms.values():
        state = [v for v in get_vars(atom) if v.get_id() not in memory_ids]
        if len(state) != 1 or not is_real(state[0]):
            continue
        variable = state[0]
        if is_eq(atom):
            if atom.arg(0).eq(variable) or atom.arg(1).eq(variable):
                # An exact feedback value becomes a parameter of the mode.
                points.append(variable)
            continue
        difference = atom.arg(0) - atom.arg(1)
        coefficient = simplify(substitute(difference, (variable, RealVal(1))) -
                               substitute(difference, (variable, RealVal(0))))
        if not is_rational_value(coefficient) or coefficient.as_fraction() == 0:
            continue
        lower = (coefficient.as_fraction() > 0) == (atom.decl().kind() in (Z3_OP_GT, Z3_OP_GE))
        bounds.setdefault(str(variable), (variable, [], []))[1 if lower else 2].append(atom)
    def fresh(atom):
        local = [v for v in memory if any(v.eq(x) for x in get_vars(atom))]
        new = [FreshReal('parameter') for _ in local]
        return substitute(atom, *zip(local, new)), new
    for _, (variable, lower, upper) in sorted(bounds.items()):
        if not lower or not upper:
            continue
        lower.sort(key=lambda t: features(t, memory)[0])
        upper.sort(key=lambda t: features(t, memory)[0])
        for point in {str(v):v for v in points}.values():
            if point.eq(variable):
                continue
            lo, lm = fresh(lower[0])
            hi, hm = fresh(upper[0])
            value = FreshReal('point')
            yield And(lo, hi, point == value), lm + hm + [value]


def bounded_state_count(formula, memory):
    """Count affine state expressions with both lower and upper conjunctive bounds."""
    memory_ids = {v.get_id() for v in memory}
    directions = {}
    def visit(expr):
        if is_and(expr):
            for child in expr.children():
                visit(child)
            return
        negated = is_not(expr)
        if negated:
            expr = expr.arg(0)
        kind = expr.decl().kind()
        if kind not in (Z3_OP_LT, Z3_OP_LE, Z3_OP_GT, Z3_OP_GE):
            return
        variables = sorted((v for v in get_vars(expr) if v.get_id() not in memory_ids),
                           key=lambda v: v.sexpr())
        if not variables or any(not is_real(v) for v in variables):
            return
        difference = simplify(expr.arg(0) - expr.arg(1))
        terms = []
        for v in variables:
            coefficient = simplify(substitute(difference, (v, RealVal(1))) -
                                   substitute(difference, (v, RealVal(0))))
            if not is_rational_value(coefficient):
                return
            if coefficient.as_fraction() != 0:
                terms.append((v, coefficient))
        if not terms:
            return
        residual = simplify(difference - Sum([v*c for v, c in terms]))
        # Finite differences alone do not establish linearity (e.g. x*x).
        if any(v.get_id() not in memory_ids for v in get_vars(residual)):
            return
        leading = terms[0][1].as_fraction()
        key = tuple((v.sexpr(), c.as_fraction()/leading) for v, c in terms)
        lower = (leading > 0) == (kind in (Z3_OP_GT, Z3_OP_GE))
        if negated:
            lower = not lower
        directions.setdefault(key, set()).add(lower)
    visit(formula)
    return sum(len(sides) == 2 for sides in directions.values())


def strict_bound_count(formula):
    """Count strict conjunctive bounds, including negated non-strict inequalities."""
    if is_and(formula):
        return sum(strict_bound_count(c) for c in formula.children())
    if formula.decl().kind() in (Z3_OP_LT, Z3_OP_GT):
        return 1
    return int(is_not(formula) and formula.arg(0).decl().kind() in (Z3_OP_LE, Z3_OP_GE))


def candidates(entries, memory, mined_only=False):
    """Order by formula structure, never benchmark name or saved template ID."""
    formulas = [And(*parse_smt2_string(e['smt2'])) for e in entries]
    ranked = sorted(range(len(formulas)), key=lambda i: features(formulas[i], memory)[0])
    plain = sorted((i for i in ranked if not features(formulas[i], memory)[1]),
                   key=lambda i: (-bounded_state_count(formulas[i], memory),
                                  -strict_bound_count(formulas[i]) if bounded_state_count(formulas[i], memory) else 0,
                                  features(formulas[i], memory)[0]))
    branching = [i for i in ranked if features(formulas[i], memory)[1]]
    for interval, interval_memory in (() if mined_only else interval_candidates(formulas, memory)):
        for index in branching[:2]:
            ts, ms = pack_memory([interval, formulas[index]], list(memory) + interval_memory)
            yield {'ids': [index], 'derived_interval': True, 'lifted_bounds': False,
                   'templates': [smt(t) for t in ts], 'memory': [str(v) for v in ms]}
    pairs = list(itertools.product(plain, branching))
    pairs += list(itertools.combinations(ranked, 2))
    subsets = pairs + [(i,) for i in ranked]
    seen = set()
    for subset in subsets:
        key = tuple(sorted(subset))
        if key in seen:
            continue
        seen.add(key)
        selected = [formulas[i] for i in subset]
        # A concrete sampled threshold may need generalization beyond the horizon.
        versions = [(False, selected, memory)]
        if not mined_only and any(features(t, memory)[0][0] for t in selected):
            lifted, lifted_memory = lift_bounds(selected, memory)
            versions.insert(0, (True, lifted, lifted_memory))
        for lifted, ts, ms in versions:
            # Put simpler modes first; selector ordering materially affects native elimination.
            ts = sorted(ts, key=lambda t: (features(t, ms)[0][1], features(t, ms)[1], features(t, ms)[0][2]))
            ts, ms = pack_memory(ts, ms)
            yield {'ids': list(subset), 'mined_only': mined_only, 'lifted_bounds': lifted,
                   'templates': [smt(t) for t in ts], 'memory': [str(v) for v in ms]}


def cross_depth_candidates(previous, current, previous_depth, current_depth):
    """Generalize a changing bound supported by two mined horizons.

    Conservatively consider parameter-free modes with one bound magnitude > 1.
    Preserve coefficients, divisors, zero and one. Require logical equivalence
    after parameterization. The fixed point and native extractor validate proposals.
    """
    if current_depth <= previous_depth:
        raise ValueError('Cross-depth evidence requires increasing depths')

    def eligible(snapshot):
        memory = [Real(n) for n in snapshot['memory']]
        for index, entry in enumerate(snapshot['templates']):
            original = And(*parse_smt2_string(entry['smt2']))
            score, _ = features(original, memory)
            if score[0] != 1 or score[1] != 0:
                continue
            lifted, parameters = lift_bounds([original], [])
            if len(parameters) != 1:
                continue
            values = set()
            def collect(expr):
                if is_rational_value(expr) and abs(expr.as_fraction()) > 1:
                    values.add(abs(expr.as_fraction()))
                for child in expr.children():
                    if (is_mul(expr) or expr.decl().kind() in (Z3_OP_DIV, Z3_OP_IDIV)) and is_rational_value(child):
                        continue
                    collect(child)
            collect(simplify(original))
            if len(values) == 1:
                yield index, next(iter(values)), lifted[0], parameters[0]

    old = sorted(eligible(previous), key=lambda t: t[1], reverse=True)
    memory = [Real(n) for n in current['memory']]
    formulas = [And(*parse_smt2_string(e['smt2'])) for e in current['templates']]
    partners = sorted(range(len(formulas)), key=lambda i: features(formulas[i], memory)[0])
    accepted = []
    # Prefer the largest observed bound: a pool may retain earlier concrete modes.
    for index, bound, formula, parameter in sorted(eligible(current), key=lambda t: t[1], reverse=True):
        for old_index, old_bound, old_formula, old_parameter in old:
            if bound == old_bound:
                continue
            solver = Solver(); solver.set(timeout=1000)
            solver.add(Xor(formula, substitute(old_formula, (old_parameter, parameter))))
            if solver.check() != unsat:
                continue
            duplicate = False
            for earlier, earlier_parameter in accepted:
                solver = Solver(); solver.set(timeout=1000)
                solver.add(Xor(formula, substitute(earlier, (earlier_parameter, parameter))))
                if solver.check() == unsat:
                    duplicate = True
                    break
            if duplicate:
                break
            accepted.append((formula, parameter))
            evidence = [{'depth': previous_depth, 'id': old_index, 'bound': str(old_bound)},
                        {'depth': current_depth, 'id': index, 'bound': str(bound)}]
            for partner in partners:
                if partner == index or features(formulas[partner], memory)[0][1] == 0:
                    continue
                ts, ms = pack_memory([formula, formulas[partner]], memory + [parameter])
                yield {'ids': [index, partner], 'mined_only': False,
                       'lifted_bounds': True, 'cross_depth_evidence': evidence,
                       'templates': [smt(t) for t in ts], 'memory': [str(v) for v in ms]}
            break


def worker(spec_path, config_path):
    import importlib
    from common.util import quantifier_eliminate
    from solver.belief_map import BeliefsMap
    from solver.forward_planner import ForwardPlanner
    from solver.template_miner import TemplateMiner
    from solver.options import SynthesisOptions
    from solver.fixpoints import FixpointCalculation
    spec, config = json.loads(Path(spec_path).read_text()), json.loads(Path(config_path).read_text())
    options = SynthesisOptions.from_mapping(spec.get('synthesis_options'))
    game = getattr(importlib.import_module(spec['module']), spec['class'])(**spec.get('kwargs', {}))
    if config['phase'] == 'mine':
        depth = config['depth']
        beliefs = ForwardPlanner(game, 0, -1).forward_planning(depth)
        if not beliefs:
            result = {'outcome': 'unrealizable'}
        else:
            levels, memory = TemplateMiner(game, True, config.get('generalization_threshold', 5), 1, options=options).mine_all(beliefs[1:2+depth])
            result = {'outcome': 'mined', 'memory': [str(v) for v in memory[1:]],
                      'templates': [{'level': level, 'smt2': smt(t)}
                                    for level in sorted(levels) for t in levels[level]]}
    else:
        initial = quantifier_eliminate(Exists(list(game.make_observable_states('org').values()),
                                             game.initial(game.make_states('org'))))
        belief_map = BeliefsMap(initial)
        memory = [Real(n) for n in config['memory']]
        for formula in config['templates']:
            belief_map.merge(And(*parse_smt2_string(formula)), memory)
        depth, _ = FixpointCalculation(game, 0, -1, options=options).fixpoint_memory(belief_map)
        result = {'outcome': 'candidate' if depth == -1 else 'inconclusive', 'fixed_point_depth': depth}
    Path('phase-result.json').write_text(json.dumps(result, indent=2)+'\n')


def synthesize(spec, simsat, max_depth=2, candidates_per_depth=4,
               mining_timeout=30, fixed_point_timeout=12, extraction_timeout=60, mined_only=False,
               cross_depth_bounds=False, whole_pool_limit=0, generalization_threshold=5,
               prune_whole_pool=False, pruning_timeout=8):
    """Search bounded horizons, or keep deepening when max_depth is None.

    Unbounded deepening relies on run_suite's overall process-group timeout.
    Per-phase limits still prevent one candidate from consuming the whole run.
    """
    if max_depth is not None and (type(max_depth) is not int or max_depth < 0):
        raise ValueError('max_depth must be a nonnegative integer or null')
    if mined_only and cross_depth_bounds:
        raise ValueError('Cross-depth generalization changes templates; it is not mined-only')
    root = Path.cwd()
    spec_path = root / 'automatic-case.json'
    spec_path.write_text(json.dumps(spec, indent=2)+'\n')
    attempts, strategy_s = [], 0.0
    started = time.perf_counter()
    module = Path(__file__).resolve()

    def save():
        (root / 'automatic-attempts.json').write_text(json.dumps(attempts, indent=2)+'\n')

    def phase(config, name, timeout):
        work = root / name
        work.mkdir()
        config_path = work / 'config.json'
        config_path.write_text(json.dumps(config, indent=2)+'\n')
        start = time.perf_counter()
        with (work / 'run.log').open('w') as log:
            try:
                # Same process group as the enclosing suite worker: the suite's
                # global timeout also kills every child. No grandchildren here.
                p = subprocess.run([sys.executable, '-u', str(module), '--worker',
                                    str(spec_path), str(config_path)], cwd=work,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                if p.returncode:
                    raise RuntimeError(f'Automatic template worker failed; see {work / "run.log"}')
                result = json.loads((work / 'phase-result.json').read_text())
            except subprocess.TimeoutExpired:
                result = {'outcome': 'timeout'}
        attempts.append({'directory': name, 'phase': config['phase'],
                         'elapsed_s': time.perf_counter()-start, **result})
        save()
        print(name, result['outcome'], flush=True)
        return result, work

    def test(config, name):
        nonlocal strategy_s
        result, work = phase({'phase': 'fixed-point', **config}, name, fixed_point_timeout)
        if result['outcome'] != 'candidate':
            return False
        invariant = root / 'invariant-outcome.json'
        if not invariant.exists():
            invariant.write_text(json.dumps({
                'outcome': 'winning-invariant',
                'invariant_s': time.perf_counter() - started - strategy_s,
                'native_strategy_confirmed': False,
                'directory': work.name,
            }, indent=2) + '\n')
        if prune_whole_pool and config.get('whole_pool'):
            original = config['templates']
            active = list(range(len(original)))
            for index in list(active):
                trial = [i for i in active if i != index]
                trial_config = {**config, 'templates': [original[i] for i in trial],
                                'retained_template_ids': trial}
                trial_result, trial_work = phase({'phase': 'fixed-point', **trial_config},
                                                 f'{name}-prune-{index}', pruning_timeout)
                if trial_result['outcome'] == 'candidate':
                    active, config, work = trial, trial_config, trial_work
        start = time.perf_counter()
        with (work / 'strategy.sexpr').open('w') as output, (work / 'strategy.stderr').open('w') as error:
            try:
                p = subprocess.run([str(simsat), '-strategy', str(work / 'result.smt2')],
                                   stdout=output, stderr=error, timeout=extraction_timeout)
                if p.returncode:
                    raise RuntimeError(f'Native strategy extraction failed; see {work / "strategy.stderr"}')
                text = (work / 'strategy.sexpr').read_text()
                match = re.match(r'\s*\((sat|unsat|unknown)\b', text)
                if not match:
                    raise RuntimeError(f'Invalid native output in {work}')
                winner = match.group(1)
                if winner == 'sat' and '(strategy' not in text:
                    raise RuntimeError('SAT without strategy')
            except subprocess.TimeoutExpired:
                winner = 'timeout'
        elapsed = time.perf_counter()-start
        strategy_s += elapsed
        attempts.append({'directory': work.name, 'phase': 'extraction', 'outcome': winner, 'elapsed_s': elapsed})
        save()
        if winner != 'sat':
            return False
        for file in ('result.smt2', 'strategy.sexpr', 'strategy.stderr'):
            shutil.copyfile(work / file, root / file)
        (root / 'automatic-selected.json').write_text(json.dumps({'directory': work.name, **config}, indent=2)+'\n')
        return True

    if test({'templates': [], 'memory': []}, 'initial-only'):
        return {'outcome': 'realizable', 'strategy_s': strategy_s}
    previous = None
    previous_depth = None
    depths = itertools.count() if max_depth is None else range(max_depth+1)
    for depth in depths:
        result, _ = phase({'phase': 'mine', 'depth': depth, 'generalization_threshold': generalization_threshold}, f'mine-{depth}', mining_timeout)
        if result['outcome'] == 'unrealizable':
            return {'outcome': 'unrealizable', 'strategy_s': strategy_s}
        if result['outcome'] != 'mined':
            continue
        memory = [Real(n) for n in result['memory']]
        if 0 < len(result['templates']) <= whole_pool_limit:
            ts, ms = pack_memory([And(*parse_smt2_string(e['smt2'])) for e in result['templates']], memory)
            config = {'whole_pool': True, 'mined_only': True, 'lifted_bounds': False,
                      'templates': [smt(t) for t in ts], 'memory': [str(v) for v in ms]}
            if test(config, f'depth-{depth}-whole-pool'):
                return {'outcome': 'realizable', 'strategy_s': strategy_s}
        choices = candidates(result['templates'], memory, mined_only=mined_only or cross_depth_bounds)
        if cross_depth_bounds and previous is not None:
            choices = itertools.chain(cross_depth_candidates(previous, result, previous_depth, depth), choices)
        for number, config in enumerate(itertools.islice(choices, candidates_per_depth)):
            if test(config, f'depth-{depth}-candidate-{number}'):
                return {'outcome': 'realizable', 'strategy_s': strategy_s}
        previous, previous_depth = result, depth
    return {'outcome': 'inconclusive', 'strategy_s': strategy_s}


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if len(sys.argv) != 4 or sys.argv[1] != '--worker':
        raise SystemExit('Internal worker; run artifact/run_cca.py instead')
    worker(sys.argv[2], sys.argv[3])

#!/usr/bin/env python3
"""Run isolated benchmark cases, including strategy extraction within the timeout."""
import argparse
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
AE = ROOT / 'artifact'


def worker(spec_file, simsat, memory_gib):
    limit = int(memory_gib * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    sys.path.insert(0, str(ROOT))
    from solver.synthesizer import Synthesizer
    from solver.options import SynthesisOptions
    spec = json.loads(Path(spec_file).read_text())
    options = SynthesisOptions.from_mapping(spec.get('synthesis_options'))
    game = getattr(importlib.import_module(spec['module']), spec['class'])(
        **spec.get('kwargs', {}))
    started = time.perf_counter()
    automatic_result = None
    if spec.get('automatic_templates'):
        from solver.automatic_templates import synthesize
        automatic_result = synthesize(spec, simsat, **spec.get("automatic_template_options", {}))
        outcome = automatic_result['outcome']
    elif 'supplied_templates' in spec:
        provider = importlib.import_module(spec.get('supplied_template_provider', 'cca_templates'))
        supplied = provider.supplied
        from z3 import BoolVal
        templates, memory = supplied(game, spec['supplied_templates'])
        outcome = Synthesizer(game, options=options).syn_strategy_with_template(
            templates, memory, BoolVal(True), spec['simulated_depth'])
    else:
        outcome = Synthesizer(game, options=options).syn_strategy_with_template_mining(*spec['args'])
    invariant_s = time.perf_counter() - started
    strategy_s = automatic_result['strategy_s'] if automatic_result else 0.0
    invariant_s -= strategy_s
    if outcome == 'realizable' and automatic_result is None:
        Path('invariant-outcome.json').write_text(json.dumps({
            'outcome': 'winning-invariant', 'invariant_s': invariant_s,
            'native_strategy_confirmed': False,
        }, indent=2) + '\n')
        query = Path('result.smt2')
        if not query.is_file():
            raise RuntimeError('Winning invariant did not export a strategy query')
        started = time.perf_counter()
        if spec.get('strategy_backend', 'native') == 'skeleton-qe':
            support_file = Path('winning-support.smt2')
            if options.export_winning_region and support_file.is_file():
                from artifact.skeleton_qe import initial_memory
                from z3 import And, parse_smt2_file
                states = game.make_states('org')
                initialization = initial_memory(
                    game.initial(states), list(states.values()),
                    And(*parse_smt2_file(str(support_file))))
                Path('initial-memory.json').write_text(
                    json.dumps(initialization, indent=2) + '\n')
            with open('skeleton.sexpr', 'w') as output, open('strategy.stderr', 'w') as error:
                subprocess.run([simsat, '-skeleton', str(query.resolve())],
                               stdout=output, stderr=error, check=True)
            from artifact.skeleton_qe import recover
            strategy_text, verification = recover(Path('skeleton.sexpr').read_text(), compact_qe=options.compact_qe)
            Path('strategy.sexpr').write_text(strategy_text)
            Path('strategy-verification.json').write_text(json.dumps(verification, indent=2) + '\n')
        elif spec.get('strategy_backend', 'native') == 'native':
            with open('strategy.sexpr', 'w') as output, open('strategy.stderr', 'w') as error:
                subprocess.run([simsat, '-strategy', str(query.resolve())],
                               stdout=output, stderr=error, check=True)
        else:
            raise ValueError('Unsupported strategy backend: ' + spec['strategy_backend'])
        strategy_s = time.perf_counter() - started
        strategy = Path('strategy.sexpr').read_text()
        if not re.match(r'\s*\(sat\b', strategy) or '(strategy' not in strategy:
            raise RuntimeError('SimSat did not return a SAT winning strategy')
    elif outcome not in ('realizable', 'unrealizable', 'inconclusive'):
        raise RuntimeError(f'Unrecognized synthesis outcome: {outcome!r}')
    Path('outcome.json').write_text(json.dumps({
        'outcome': outcome, 'invariant_s': invariant_s,
        'strategy_s': strategy_s, 'solving_s': invariant_s + strategy_s,
    }, indent=2) + '\n')


def main(default_manifest=AE / 'benchmarks/uav.json'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=default_manifest)
    parser.add_argument('--trace', action='store_true', help='Log fixed-point phases and iteration numbers')
    parser.add_argument('--available', action='store_true',
                        help='Run manifest cases without requiring a complete Table 1 family mapping')
    parser.add_argument('--case', action='append', help='Select a case (requires --available)')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--memory-gib', type=float, default=64)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--simsat', type=Path, default=AE / 'bin/simsat')
    args = parser.parse_args()
    if args.timeout <= 0 or args.memory_gib <= 0:
        parser.error('Resource limits must be positive')
    manifest = json.loads(args.manifest.read_text())
    cases = manifest['instances']
    names = [case['name'] for case in cases]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'[\w-]+', n) for n in names):
        parser.error('Case names must be unique safe directory names')
    paper = manifest['paper']
    complete = (manifest.get('table_i_mapping_confirmed') is True
                and len(cases) == paper['instances']
                and sum(c.get('expected') == 'realizable' for c in cases) == paper['sat']
                and sum(c.get('expected') == 'unrealizable' for c in cases) == paper['unsat'])
    if not args.available and not complete:
        parser.error('Table I mapping is incomplete: need all cases and expected labels. '
                     'Use --available for explicitly partial runs.')
    if args.case:
        if not args.available or set(args.case) - set(names):
            parser.error('--case requires --available and known case names')
        cases = [c for c in cases if c['name'] in args.case]
    simsat = args.simsat.resolve()
    if not os.access(simsat, os.X_OK):
        parser.error('SimSat is missing; run artifact/build.sh first')
    out = (args.output or AE / 'results' / time.strftime('%Y%m%dT%H%M%S')).resolve()
    out.mkdir(parents=True, exist_ok=False)
    versions = AE / '_build/versions.txt'
    if versions.is_file():
        shutil.copyfile(versions, out / 'build-versions.txt')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # Record the actual Python sources, including uncommitted artifact integration.
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for folder in ('common', 'solver', 'examples', 'artifact')
              for p in (ROOT / folder).glob('**/*.py' if folder == 'examples' else '*.py')}
    cpu_model = None
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        cpu_model = next((line.split(':', 1)[1].strip()
                          for line in cpuinfo.read_text().splitlines()
                          if line.startswith('model name')), None)
    (out / 'environment.json').write_text(json.dumps({
        'platform': platform.platform(), 'python': sys.version,
        'cpu_model': cpu_model, 'logical_cpus': os.cpu_count(),
        'timeout_s': args.timeout, 'memory_gib_per_process': args.memory_gib,
        'simsat': str(simsat), 'source_sha256': hashes,
        'partial': args.available, 'trace': args.trace,
    }, indent=2) + '\n')
    rows = []
    for case in cases:
        work = out / case['name']
        work.mkdir()
        spec = work / 'case.json'
        spec.write_text(json.dumps(case))
        started = time.perf_counter()
        status = 'error'
        env = os.environ.copy()
        if args.trace:
            env['POGAME_TRACE'] = '1'
        with (work / 'run.log').open('w') as log:
            process = subprocess.Popen(
                [sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
                 str(spec), str(simsat), str(args.memory_gib)],
                cwd=work, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
            try:
                code = process.wait(timeout=args.timeout)
                if code == 0 and (work / 'outcome.json').is_file():
                    status = 'solved'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                status = 'timeout'
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        result = json.loads((work / 'outcome.json').read_text()) if status == 'solved' else {}
        if status == 'solved' and result['outcome'] == 'inconclusive':
            status = 'inconclusive'
        if status == 'solved' and case.get('expected') not in (None, result['outcome']):
            status = 'mismatch'
        row = {'name': case['name'], 'status': status, 'returncode': process.returncode,
               'expected': case.get('expected'),
               'wall_s': time.perf_counter() - started, **result}
        invariant_file = work / 'invariant-outcome.json'
        invariant = json.loads(invariant_file.read_text()) if invariant_file.is_file() else {}
        row['winning_invariant_found'] = bool(invariant) or result.get('outcome') == 'realizable'
        row['strategy_extracted'] = result.get('outcome') == 'realizable'
        if invariant and 'invariant_s' not in row:
            row['invariant_s'] = invariant['invariant_s']
        rows.append(row)
        (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(f"{case['name']}: {status} ({row['wall_s']:.2f}s)", flush=True)
    with (out / 'results.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'status', 'returncode', 'expected', 'outcome',
            'invariant_s', 'strategy_s', 'solving_s', 'wall_s', 'winning_invariant_found', 'strategy_extracted'])
        writer.writeheader()
        writer.writerows(rows)
    solved = [r for r in rows if r['status'] == 'solved']
    times = [r['solving_s'] for r in solved]
    summary = {
        'family': manifest.get('family'),
        'reconstructed_cases': [c['name'] for c in cases if c.get('reconstructed')],
        'partial': args.available, 'instances': len(rows), 'solved': len(solved),
        'winning_invariants': sum(r['winning_invariant_found'] for r in rows),
        'extracted_strategies': sum(r['strategy_extracted'] for r in rows),
        'sat': sum(r['outcome'] == 'realizable' for r in solved),
        'unsat': sum(r['outcome'] == 'unrealizable' for r in solved),
        'mean_s': statistics.mean(times) if times else None,
        'median_s': statistics.median(times) if times else None,
        'max_s': max(times) if times else None,
        'paper_reference': manifest['paper'],
    }
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    print(f'Logs, queries, strategies, and CSV: {out}')
    return 0 if len(solved) == len(rows) else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    else:
        sys.exit(main())

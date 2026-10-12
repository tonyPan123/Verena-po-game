"""Opt-in generalization of exact point beliefs to memory-parameterized cubes."""
from z3 import And, Int, Real, Solver, Xor, is_arith, is_int, is_rational_value, is_int_value, sat, unsat
from z3.z3util import get_vars


def generalize_points(templates, memory, latent, domains=None):
    """Lift all coordinates together only after proving exact point equivalence.

    Each concrete point remains an instance. New valuations are candidates:
    the existing backward fixed point must establish their winning subset.
    """
    domains=domains or {}
    allowed={v.get_id() for v in latent}
    result={};seen=set();parameters=list(memory)
    for level, formulas in templates.items():
        for formula in formulas:
            variables=sorted(get_vars(formula),key=str)
            if len(variables)<2 or any(v.get_id() not in allowed or not is_arith(v) for v in variables):
                result.setdefault(level,[]).append(formula);continue
            solver=Solver();solver.set(timeout=2000);solver.add(formula)
            if solver.check()!=sat:
                result.setdefault(level,[]).append(formula);continue
            model=solver.model();values=[model.eval(v,model_completion=True) for v in variables]
            if any(not (is_rational_value(v) or is_int_value(v)) for v in values):
                result.setdefault(level,[]).append(formula);continue
            point=And(*[v==value for v,value in zip(variables,values)])
            check=Solver();check.set(timeout=2000);check.add(Xor(formula,point))
            if check.check()!=unsat:
                result.setdefault(level,[]).append(formula);continue
            key=tuple((str(v),str(v.sort())) for v in variables)
            if key in seen:continue
            seen.add(key)
            local=[]
            for v in variables:
                name=f'm{len(parameters)}'
                parameter=Int(name) if is_int(v) else Real(name)
                parameters.append(parameter);local.append(parameter)
            from z3 import Or
            constraints=[v==m for v,m in zip(variables,local)]
            constraints.extend(Or(*[m==value for value in domains[str(v)]])
                               for v,m in zip(variables,local) if str(v) in domains)
            result.setdefault(len(local),[]).append(And(*constraints))
    return result,parameters


def infer_finite_domains(game):
    """Keep only syntactic finite-domain candidates proven inductive by SMT."""
    from z3 import Or, Not, substitute, is_eq, is_le, is_ge, is_lt, is_gt
    current,successor,action=game.make_states('org'),game.make_states('prime'),game.make_actions('domain')
    transition=game.transition_env(current,successor,action)
    formulas=[game.initial(current),game.safety(current),transition]
    candidates={}
    for name in game.latent_states:
        variable=current[name]
        if not is_arith(variable):continue
        ids={variable.get_id(),successor[name].get_id()};values={}
        def visit(expr):
            if (is_eq(expr) or is_le(expr) or is_ge(expr) or is_lt(expr) or is_gt(expr)) and expr.num_args()==2:
                for left,right in (expr.children(),list(reversed(expr.children()))):
                    if left.get_id() in ids and (is_rational_value(right) or is_int_value(right)):
                        values[right.sexpr()]=right
            for child in expr.children():visit(child)
        for formula in formulas:visit(formula)
        if 1<=len(values)<=16:
            domain=Or(*[variable==v for v in values.values()])
            check=Solver();check.set(timeout=2000);check.add(game.initial(current),Not(domain))
            if check.check()==unsat:candidates[name]=list(values.values())
    while candidates:
        domain=And(*[Or(*[current[k]==v for v in values]) for k,values in candidates.items()])
        invalid=[]
        for name,values in candidates.items():
            target=Or(*[successor[name]==v for v in values])
            check=Solver();check.set(timeout=2000)
            check.add(domain,game.enable_action(action),transition,Not(target))
            if check.check()!=unsat:invalid.append(name)
        if not invalid:break
        for name in invalid:del candidates[name]
    return {str(current[name]):values for name,values in candidates.items()}

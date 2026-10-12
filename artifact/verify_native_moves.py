"""Independently verify single-output native strategy trees and coverage."""
import re
from pathlib import Path
from z3 import *
from z3.z3util import get_vars
def unpack(formula):
    if is_and(formula) and formula.num_args()==1:formula=formula.arg(0)
    levels=[]
    while is_quantifier(formula):
        variables=[Const(str(formula.var_name(i)),formula.var_sort(i)) for i in range(formula.num_vars())]
        levels.append((formula.is_forall(),variables))
        formula=substitute_vars(formula.body(),*reversed(variables))
    return levels,formula



def parse(text):
    tokens=iter(re.findall(r'\(|\)|[^\s()]+',text))
    def item(token):
        if token!='(':return token
        result=[]
        for token in tokens:
            if token==')':return result
            result.append(item(token))
        raise ValueError('Unclosed s-expression')
    result=item(next(tokens))
    if next(tokens,None) is not None:raise ValueError('Extra native output')
    return result


def sexpr(node):
    return '('+' '.join(map(sexpr,node))+')' if isinstance(node,list) else node


def verify(query_file,strategy_file):
    levels,matrix=unpack(And(*parse_smt2_file(str(query_file))))
    outputs=[v for universal,vs in levels if not universal for v in vs]
    if len(outputs)!=1:raise ValueError('Verifier requires one existential output')
    output=outputs[0];variables={str(v):v for _,vs in levels for v in vs}
    tree=parse(Path(strategy_file).read_text())
    if tree[0]!='sat':raise ValueError('No SAT strategy')
    prefix=tree[1];strategy=tree[2]
    if prefix[0]!='prefix' or strategy[0]!='strategy':raise ValueError('Unexpected native output')
    declarations={};native_output=None
    for quantifier,name,sort in prefix[1:]:
        original=name.rsplit('!',1)[0]
        if original not in variables or str(variables[original].sort())!=sort:raise ValueError('Native prefix mismatch')
        declarations[name]=variables[original]
        if quantifier=='exists':
            if original!=str(output) or native_output is not None:raise ValueError('Native output mismatch')
            native_output=name
    if native_output is None:raise ValueError('Native strategy lost its move variable')
    guards=[]
    for case in strategy[1:]:
        if case[0]!='case' or len(case)!=4 or case[3]!=['strategy']:raise ValueError('Unexpected strategy nesting')
        guard=And(*parse_smt2_string('(assert '+sexpr(case[1])+')',decls=declarations))
        equation=And(*parse_smt2_string('(assert (= '+native_output+' '+sexpr(case[2])+'))',decls=declarations))
        if str(output) in {str(v) for v in get_vars(guard)}:raise ValueError('Guard depends on its output')
        # Equation must define its output once, with no self-dependence.
        expression=equation.arg(0).arg(1)
        if str(output) in {str(v) for v in get_vars(expression)}:raise ValueError('Self-dependent native move')
        solver=Solver();solver.set(timeout=10000);solver.add(guard,equation,Not(matrix))
        if solver.check()!=unsat:raise ValueError('Native branch violates certified move relation')
        guards.append(guard)
    solver=Solver();solver.set(timeout=10000);solver.add(Not(Or(*guards)))
    if solver.check()!=unsat:raise ValueError('Native strategy does not cover every input')
    return {'output':str(output),'branches':len(guards),'branch_validity':'unsat','coverage':'unsat'}

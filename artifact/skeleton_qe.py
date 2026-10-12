#!/usr/bin/env python3
"""Recover guarded Skolem moves from a winning skeleton using QE.

At an existential node, each branch's guard is its continuation's winning
region. At a universal node, universally project the continuation region.
Verify coverage, information flow, and the original matrix independently.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from z3 import *
from z3.z3util import get_vars as legacy_get_vars
from artifact.verify_native_moves import parse,sexpr


def expression_nodes(expression):
    """Visit each shared Z3 subexpression once, rather than expanding its DAG."""
    pending=[expression];seen=set()
    while pending:
        node=pending.pop()
        if node.get_id() in seen:continue
        seen.add(node.get_id())
        yield node
        pending.extend(node.children())


def get_vars(expression):
    return [node for node in expression_nodes(expression)
            if is_const(node) and node.decl().kind()==Z3_OP_UNINTERPRETED]


def initial_memory(initial, states, support, timeout_ms=30000):
    """Choose one memory that covers every initial concrete state."""
    state_ids={variable.get_id() for variable in states}
    memory=sorted((v for v in get_vars(support) if v.get_id() not in state_ids),key=str)
    solver=Solver();solver.set(timeout=timeout_ms)
    solver.add(ForAll(states,Implies(initial,support)))
    if solver.check()!=sat:raise ValueError('No certified initial memory')
    model=solver.model()
    values=[model.eval(variable,model_completion=True) for variable in memory]
    instantiated=substitute(support,list(zip(memory,values))) if memory else support
    check=Solver();check.set(timeout=timeout_ms)
    check.add(initial,Not(instantiated))
    if check.check()!=unsat:raise ValueError('Initial memory fails initial-state inclusion')
    return {'values':{str(v):value.sexpr() for v,value in zip(memory,values)},
            'verification':'unsat for initial-state inclusion violation'}


def recover(text,qe_timeout_ms=30000, *, compact_qe=False):
    variables_in = get_vars if compact_qe else legacy_get_vars
    tree=parse(text)
    if tree[0]!='sat' or len(tree)!=4:raise ValueError('A SAT winning skeleton is required')
    prefix,matrix_node,node=tree[1:]
    if prefix[0]!='prefix' or matrix_node[0]!='matrix':raise ValueError('Malformed skeleton')
    decls={};copies={};sorts={'Int':IntSort(),'Real':RealSort(),'Bool':BoolSort()}
    for _,name,sort in prefix[1:]:decls[name]=Const(name,sorts[sort])
    def collect(n):
        if n[0]=='forall':
            original,copy=n[1:3]
            decls[copy[0]]=Const(copy[0],sorts[copy[1]])
            copies[copy[0]]=decls[original[0]];collect(n[3])
        elif n[0]=='exists':
            for move in n[2:]:collect(move[2])
        elif n!=['leaf']:raise ValueError('Malformed skeleton node')
    collect(node)
    matrix=parse_smt2_string('(assert '+sexpr(matrix_node[1])+')',decls=decls)[0]
    statistics={'qe_calls':0,'branches':0}
    def apply(f,bindings):return substitute(f,list(bindings.items())) if bindings else f
    def visit(n,bindings):
        if n==['leaf']:return simplify(apply(matrix,bindings)),['strategy']
        if n[0]=='forall':
            quantified_vars=[];extended=dict(bindings)
            while n[0]=='forall':
                original,copy=decls[n[1][0]],decls[n[2][0]]
                extended[original]=copy;quantified_vars.append(copy);n=n[3]
            region,strategy=visit(n,extended)
            free={str(v) for v in variables_in(region)}
            quantified_vars=[v for v in quantified_vars if str(v) in free]
            if quantified_vars:
                statistics['qe_calls']+=1
                if compact_qe:
                    print('QE block',statistics['qe_calls'],'variables',len(quantified_vars),flush=True)
                else:
                    print('QE block',statistics['qe_calls'],'variables',len(quantified_vars),'bytes',len(region.sexpr()),flush=True)
                region=TryFor(Then('qe2','simplify'),qe_timeout_ms)(ForAll(quantified_vars,region)).as_expr()
                if compact_qe:
                    has_quantifiers = any(is_quantifier(f) for f in expression_nodes(region))
                else:
                    def quantified(f):return is_quantifier(f) or any(quantified(c) for c in f.children())
                    has_quantifiers = quantified(region)
                if has_quantifiers:raise RuntimeError('Incomplete QE')
            return simplify(region),strategy
        variable=decls[n[1][0]];regions=[];cases=[]
        for move in n[2:]:
            term=parse_smt2_string('(assert (= '+n[1][0]+' '+sexpr(move[1])+'))',decls=decls)[0].arg(1)
            term=apply(term,bindings)
            region,child=visit(move[2],{**bindings,variable:term})
            guard=simplify(And(region,Not(Or(*regions))))
            regions.append(region)
            if not is_false(guard):cases.append(['case',guard,term,child]);statistics['branches']+=1
        return simplify(Or(*regions)),['strategy',*cases]
    region,strategy=visit(node,{})
    solver=Solver();solver.set(timeout=qe_timeout_ms);solver.add(Not(region))
    if solver.check()!=unsat:raise ValueError('Skeleton does not cover the whole quantified query')
    renaming=[(decls[copy],original) for copy,original in copies.items()]
    def render(strategy):
        return ['strategy',*[
            ['case',parse(substitute(case[1],renaming).sexpr()),parse(substitute(case[2],renaming).sexpr()),render(case[3])]
            for case in strategy[1:]]]
    if compact_qe:
        # Keep shared arithmetic atoms in SMT let bindings. Expanding them in
        # every nested guard can make printing dwarf QE and verification.
        previous_alias_size=get_param('pp.min_alias_size')
        try:
            set_param('pp.min_alias_size',1)
            result=['sat',prefix,render(strategy)]
        finally:
            set_param('pp.min_alias_size',previous_alias_size)
    else:
        result=['sat',prefix,render(strategy)]
    serialized=sexpr(result)+'\n'
    verification=verify(prefix,matrix,decls,result[2],qe_timeout_ms,compact_qe=compact_qe)
    return serialized,{**statistics,**verification}


def verify(prefix,matrix,decls,strategy,timeout_ms=30000, *, compact_qe=False):
    """Check all emitted branches against the original matrix, without QE."""
    entries=prefix[1:];leaves=0;coverage=0
    variable_cache={}
    def variable_names(expression):
        # Guards at different strategy levels share most of their atoms.
        # Keep AST references in the cache so Z3 cannot recycle their IDs.
        pending=[(expression,False)]
        while pending:
            node,expanded=pending.pop();key=node.get_id()
            if key in variable_cache:continue
            if is_const(node):
                names=frozenset([str(node)]) if node.decl().kind()==Z3_OP_UNINTERPRETED else frozenset()
            elif expanded:
                names=frozenset().union(*(variable_cache[c.get_id()][1] for c in node.children()))
            else:
                pending.append((node,True))
                pending.extend((child,False) for child in node.children())
                continue
            variable_cache[key]=(node,names)
        return variable_cache[expression.get_id()][1]
    def prove(formula,message):
        solver=Solver();solver.set(timeout=timeout_ms);solver.add(formula)
        if solver.check()!=unsat:raise ValueError(message)
    def visit(index,node,bindings,path,available):
        nonlocal leaves,coverage
        while index<len(entries) and entries[index][0]=='forall':
            available=available|{entries[index][1]};index+=1
        if index==len(entries):
            if node!=['strategy']:raise ValueError('Extra strategy levels')
            instantiated=substitute(matrix,list(bindings.items())) if bindings else matrix
            prove(And(path,Not(instantiated)),'Invalid strategy leaf');leaves+=1;return
        _,name,_=entries[index];variable=decls[name];guards=[]
        for case in node[1:]:
            guard=parse_smt2_string('(assert '+sexpr(case[1])+')',decls=decls)[0]
            term=parse_smt2_string('(assert (= '+name+' '+sexpr(case[2])+'))',decls=decls)[0].arg(1)
            if bindings:
                guard=substitute(guard,list(bindings.items()));term=substitute(term,list(bindings.items()))
            if compact_qe:
                used=variable_names(guard)|variable_names(term)
                if name in used:raise ValueError('Self-dependent move')
                if not used<=available:
                    raise ValueError('Strategy uses hidden or future variables')
            else:
                if not {str(v) for v in legacy_get_vars(And(guard,variable==term)) if str(v)!=name}<=available:
                    raise ValueError('Strategy uses hidden or future variables')
                if variable in legacy_get_vars(term) or variable in legacy_get_vars(guard):raise ValueError('Self-dependent move')
            guards.append(guard)
            visit(index+1,case[3],{**bindings,variable:term},And(path,guard),available)
        prove(And(path,Not(Or(*guards))),'Incomplete branch coverage');coverage+=1
    visit(0,strategy,{},BoolVal(True),set())
    return {'verified_leaves':leaves,'coverage_checks':coverage,'verification':'unsat for every violation'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('skeleton',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compact-qe', action='store_true')
    args=parser.parse_args();text,evidence=recover(args.skeleton.read_text(),compact_qe=args.compact_qe);args.output.write_text(text)
    args.output.with_suffix('.verification.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))

if __name__=='__main__':main()

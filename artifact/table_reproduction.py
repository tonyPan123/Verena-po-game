"""Run Table 1 and Table 3 experiments and compare measured results with paper values."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import time
AE=Path(__file__).resolve().parent
FAMILIES={'uav':'uav.json','robot':'robot.json','cca':'cca.json','lander':'lander.json','finite-action':'finite-action.json'}
METHODS=['original','trivial-support','support-as-win','suffix-1','suffix-2','suffix-3']
COUNTS={'uav':[6,0,3,5,5,5],'robot':[10,0,2,2,2,2],
        'cca':[9,1,3,3,3,3],'lander':[4,0,2,2,2,2],'finite-action':[15,5,5,10,15,15]}
GAPS={
    'finite-action':'Bakery, Parts, and Robot models with finite action menus. Historical model identity and Table 3 ablation counts are not validated.',
    'robot':'Robot models with action limits 1..5. Historical parameter matching is unconfirmed.',
    'cca':'Ten CCA models with per-case synthesis settings in artifact/benchmarks/cca.json. Historical parameter matching is unconfirmed.',
    'lander':'Uniform and exponential MPL models, each with one realizable and one unrealizable instance. Current parameters are in artifact/benchmarks/lander.json.',
}


def coverage(table,families):
    rows=[]
    for family in families:
        manifest=json.loads((AE/'benchmarks'/FAMILIES[family]).read_text())
        rows.append({'family':family,'available':len(manifest['instances']),
                     'paper_instances':manifest['paper']['instances'],
                     'historical_mapping_confirmed':manifest.get('table_i_mapping_confirmed',False),
                     'note':GAPS.get(family,'Configurations are in artifact/benchmarks/uav.json.')})
    return rows


def main(table):
    p=argparse.ArgumentParser(description=f'Run available Table {table} experiments and report reproduction gaps.')
    available={k:v for k,v in FAMILIES.items() if table==3 or k!='finite-action'}
    p.add_argument('--family',choices=available,action='append')
    p.add_argument('--case',action='append',help='Select cases from one explicitly selected family')
    p.add_argument('--method',choices=METHODS,action='append',help='Table 3 only; defaults to all six columns')
    p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--memory-gib',type=float,default=64)
    p.add_argument('--jobs',type=int,default=1,help='Concurrent ablation cases; original runs remain sequential')
    p.add_argument('--trace',action='store_true')
    p.add_argument('--skip-bakery',action='store_true',help='Exclude Bakery from finite-action cases')
    p.add_argument('--dry-run',action='store_true',help='Print coverage and commands without running experiments')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.timeout<=0 or args.memory_gib<=0 or args.jobs<1:p.error('Limits must be positive')
    if table==1 and args.method:p.error('--method applies only to Table 3')
    families=list(dict.fromkeys(args.family or available))
    if args.case and len(families)!=1:p.error('--case requires exactly one --family')
    out=(args.output or AE/'results'/time.strftime(f'table{table}-%Y%m%dT%H%M%S')).resolve()
    methods=list(dict.fromkeys(args.method or METHODS)) if table==3 else ['original']
    report={'table':table,'coverage':coverage(table,families),
            'full_paper_reproduction':False,'selected_families':families,'selected_methods':methods,
            'note':'Available experiments only; counts, benchmark identities, and paper matches must be inspected separately.'}
    report['excluded_families']=['bakery'] if args.skip_bakery else []
    if args.skip_bakery:
        for row in report['coverage']:
            if row['family']=='finite-action':
                row['available']=10
                row['excluded']=5
                row['note']+=' Bakery excluded by --skip-bakery.'
    plans=[]
    for family in families:
        manifest=AE/'benchmarks'/FAMILIES[family]
        names={c['name'] for c in json.loads(manifest.read_text())['instances']}
        selected_cases=args.case or []
        if family=='finite-action' and args.skip_bakery:
            selected_cases=[name for name in (args.case or sorted(names)) if not name.startswith('bakery-')]
            if not selected_cases:p.error('No cases remain after excluding Bakery')
        if args.case and not set(args.case)<=names:p.error(f'Unknown case for {family}')
        shared=['--manifest',str(manifest),'--timeout',str(args.timeout),'--memory-gib',str(args.memory_gib)]
        for case in selected_cases:shared += ['--case',case]
        if args.trace:shared += ['--trace']
        if 'original' in methods:
            command=[sys.executable,str(AE/'run_suite.py'),'--available',*shared,'--output',str(out/family/'original')]
            plans.append({'family':family,'methods':['original'],'command':command,'directory':out/family/'original'})
        ablations=[method for method in methods if method!='original']
        if ablations:
            reference=out/(family+'-paper-reference.json')
            command=[sys.executable,str(AE/'run_table3_uav.py'),*shared,'--jobs',str(args.jobs),
                     '--paper-reference',str(reference),'--output',str(out/family/'ablations')]
            for method in ablations:command += ['--method',method]
            plans.append({'family':family,'methods':ablations,'command':command,'directory':out/family/'ablations'})
    print(json.dumps(report,indent=2),flush=True)
    if args.dry_run:
        for plan in plans:print(shlex.join(plan['command']))
        return 0
    if 'finite-action' in families:
        subprocess.run([sys.executable,str(AE/'prepare_figure3.py')],check=True)
    out.mkdir(parents=True,exist_ok=False)
    (out/'coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    for family in families:
        (out/(family+'-paper-reference.json')).write_text(json.dumps(dict(zip(METHODS,COUNTS[family])),indent=2)+'\n')
    results=[];invocations=[]
    for plan in plans:
        family=plan['family'];(out/family).mkdir(exist_ok=True)
        log=out/family/('original-runner.log' if plan['methods']==['original'] else 'ablation-runner.log')
        print(f"Running {family}: {', '.join(plan['methods'])}; log: {log}",flush=True)
        with log.open('w') as stream:
            process=subprocess.run(plan['command'],stdout=stream,stderr=subprocess.STDOUT)
        invocations.append({'family':family,'methods':plan['methods'],'returncode':process.returncode,'log':str(log)})
        source=plan['directory']/'results.json'
        if source.exists():
            for row in json.loads(source.read_text()):
                results.append({'family':family,'method':row.get('method','original'),**row})
        (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        (out/'invocations.json').write_text(json.dumps(invocations,indent=2)+'\n')
    comparisons=[]
    for family in families:
        for method in methods:
            selected=[r for r in results if r['family']==family and r['method']==method]
            counts=Counter(r['status'] for r in selected)
            reference=COUNTS[family][METHODS.index(method)]
            manifest=json.loads((AE/'benchmarks'/FAMILIES[family]).read_text())
            full_scope=len(selected)==len(manifest['instances'])==manifest['paper']['instances']
            solved=[r for r in selected if r['status']=='solved']
            timings=[r['solving_s'] for r in solved if 'solving_s' in r]
            comparisons.append({'family':family,'method':method,'completed_records':len(selected),
                                'complete_count_scope':full_scope,
                                'sat':sum(r.get('outcome')=='realizable' for r in solved),
                                'unsat':sum(r.get('outcome')=='unrealizable' for r in solved),
                                'mean_s':statistics.mean(timings) if timings else None,
                                'median_s':statistics.median(timings) if timings else None,
                                'max_s':max(timings) if timings else None,
                                'paper_table1':manifest['paper'] if method=='original' else None,
                                'solved':counts['solved'],'paper_solved':reference,
                                'winning_invariants':sum(r['winning_invariant_found'] for r in selected)
                                    if selected and all('winning_invariant_found' in r for r in selected) else None,
                                'extracted_strategies':sum(r['strategy_extracted'] for r in selected)
                                    if selected and all('strategy_extracted' in r for r in selected) else None,
                                'aggregate_count_matches':counts['solved']==reference if full_scope else None,
                                'statuses':dict(counts)})
    report.update(comparison=comparisons,invocations=invocations)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    columns=['family','method','name','status','expected','outcome','winning_invariant_found','strategy_extracted','invariant_s','solving_s','wall_s']
    with (out/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(results)
    print(f'Results and coverage report: {out}',flush=True)
    return 1 if any(p['returncode']!=0 for p in invocations) else 0

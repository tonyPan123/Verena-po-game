#!/usr/bin/env python3
"""Reproduce Figure 3: run Verena on finite-action RQ2 inputs."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import json
from pathlib import Path
import subprocess
import sys
import time
AE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--family',choices=['bakery','parts','robot'],action='append')
    p.add_argument('--case',action='append')
    p.add_argument('--skip-bakery',action='store_true',help='Exclude Bakery cases')
    p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--memory-gib',type=float,default=64)
    p.add_argument('--jobs',type=int,default=1,help='Use 1 for timing comparisons; concurrency is recorded')
    p.add_argument('--output',type=Path)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if args.jobs<1 or args.timeout<=0 or args.memory_gib<=0:p.error('Limits must be positive')
    if not args.dry_run:
        subprocess.run([sys.executable,str(AE/'prepare_figure3.py')],check=True)
    manifest=json.loads((AE/'benchmarks/finite-action.json').read_text())
    cases=[c for c in manifest['instances'] if not args.family or c['family'] in args.family]
    if args.skip_bakery:cases=[c for c in cases if c['family']!='bakery']
    if not cases:p.error('No cases selected')
    if args.case:
        if set(args.case)-{c['name'] for c in cases}:p.error('Unknown case')
        cases=[c for c in cases if c['name'] in args.case]
    output=(args.output or AE/'results'/time.strftime('figure3-%Y%m%dT%H%M%S')).resolve()
    tasks=[]
    for case in cases:
        dest=output/'po-game'/case['name']
        command=[sys.executable,str(AE/'run_suite.py'),'--available',
                 '--manifest',str(AE/'benchmarks/finite-action.json'),
                 '--case',case['name'],'--timeout',str(args.timeout),
                 '--memory-gib',str(args.memory_gib),'--output',str(dest)]
        tasks.append((case,dest,command))
    config={'excluded_families':['bakery'] if args.skip_bakery else [],'concurrent_jobs':args.jobs,'timeout_s':args.timeout,'limits_per_process_gib':args.memory_gib,
            'full_paper_reproduction':False,
            'commands':[task[-1] for task in tasks]}
    if args.dry_run:print(json.dumps(config,indent=2));return 0
    output.mkdir(parents=True,exist_ok=False)
    (output/'configuration.json').write_text(json.dumps(config,indent=2)+'\n')
    def run(task):
        case,dest,command=task
        dest.parent.mkdir(parents=True,exist_ok=True)
        with (dest.parent/(case['name']+'.runner.log')).open('w') as f:
            result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
        results=dest/'results.json'
        row=json.loads(results.read_text())[0] if results.exists() else {'outcome':'error','returncode':result.returncode}
        if row.get('status')=='timeout':row['outcome']='timeout'
        elif row.get('status')=='error':row['outcome']='error'
        row.update(tool='po-game',family=case['family'],actions=case['paper_actions'],concurrent_jobs=args.jobs)
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(run,t) for t in tasks]
        for future in as_completed(futures):
            row=future.result();rows.append(row)
            print(f'{row["tool"]} {row.get("name")}: {row.get("outcome")} {row.get("wall_s",0):.2f}s',flush=True)
            (output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    fields=['tool','family','name','actions','outcome','wall_s','concurrent_jobs']
    with (output/'results.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    summary={'full_paper_reproduction':False,
             'results':{'po-game':{status:sum(r['outcome']==status for r in rows) for status in ('realizable','unrealizable','timeout','inconclusive','error')}}}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return int(any(r['outcome']=='error' for r in rows))


if __name__=='__main__':raise SystemExit(main())

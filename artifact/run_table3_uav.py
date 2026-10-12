#!/usr/bin/env python3
"""Run Table 3 ablations for a benchmark manifest; default to UAV."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
AE = ROOT / 'artifact'
METHODS = {'trivial-support': None, 'support-as-win': None,
           'suffix-1': 0, 'suffix-2': 1, 'suffix-3': 2}
PAPER = {'original': 6, 'trivial-support': 0, 'support-as-win': 3,
         'suffix-1': 5, 'suffix-2': 5, 'suffix-3': 5}


def classify(method, answer):
    if answer == 'Good':
        return 'realizable'
    if answer == 'Bad':
        return 'inconclusive' if method == 'trivial-support' else 'unrealizable'
    if answer == 'Inconclusive':
        return 'inconclusive'
    raise RuntimeError(f'Unexpected baseline answer: {answer!r}')


def worker(spec_file, method, simsat, memory_gib):
    limit = int(float(memory_gib) * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    sys.path.insert(0, str(ROOT))
    from solver.synthesizer import Synthesizer
    from solver.options import SynthesisOptions
    case = json.loads(Path(spec_file).read_text())
    options = SynthesisOptions.from_mapping(case.get('synthesis_options'))
    game = getattr(importlib.import_module(case['module']), case['class'])(**case.get('kwargs', {}))
    syn = Synthesizer(game, options=options)
    attempts = []

    def extract(query):
        number = len(attempts) + 1
        stem = f'extraction-{number:03d}'
        shutil.copyfile(query, stem + '.smt2')
        begin = time.perf_counter()
        backend = case.get('strategy_backend', 'native')
        if backend not in ('native', 'skeleton-qe'):
            raise ValueError('Unsupported ablation strategy backend: ' + backend)
        flag = '-skeleton' if backend == 'skeleton-qe' else '-strategy'
        raw_file = stem + ('.skeleton.sexpr' if backend == 'skeleton-qe' else '.sexpr')
        with open(raw_file, 'w') as output, open(stem + '.stderr', 'w') as error:
            result = subprocess.run([simsat, flag, str(Path(query).resolve())],
                                    stdout=output, stderr=error)
        text = Path(raw_file).read_text()
        if backend == 'skeleton-qe' and result.returncode == 0 and re.match(r'\s*\(sat\b', text):
            from artifact.skeleton_qe import recover
            text, verification = recover(text, compact_qe=options.compact_qe)
            Path(stem + '.sexpr').write_text(text)
            Path(stem + '.verification.json').write_text(json.dumps(verification, indent=2) + '\n')
        elapsed = time.perf_counter() - begin
        match = re.match(r'\s*\((sat|unsat|unknown)\b', text)
        winner = match.group(1) if match else 'invalid'
        attempts.append({'query': stem + '.smt2', 'winner': winner,
                         'seconds': elapsed, 'returncode': result.returncode, 'backend': backend})
        Path('extractions.json').write_text(json.dumps(attempts, indent=2) + '\n')
        if result.returncode != 0 or winner == 'invalid':
            raise RuntimeError(f'Strategy extractor failed: {attempts[-1]}')
        if winner == 'sat' and '(strategy' not in text:
            raise RuntimeError('SAT without a strategy is not a solved case')
        return winner

    start = time.perf_counter()
    if method == 'trivial-support':
        answer = syn.backward_only_baseline(game)
        if answer == 'Good' and extract('result.smt2') != 'sat':
            answer = 'Inconclusive'
    elif method == 'support-as-win':
        answer = syn.forward_planning_baseline(game, is_real=True, strategy_extractor=extract)
    else:
        answer = syn.fix_memory_baseline(game, METHODS[method], strategy_extractor=extract)
    elapsed = time.perf_counter() - start
    outcome = classify(method, answer)
    Path('outcome.json').write_text(json.dumps({
        'outcome': outcome, 'raw_answer': answer, 'solving_s': elapsed,
        'strategy_s': sum(a['seconds'] for a in attempts), 'extraction_attempts': len(attempts),
    }, indent=2) + '\n')


def run_one(case, method, out, args):
    work = out / method / case['name']
    work.mkdir(parents=True)
    spec = work / 'case.json'
    spec.write_text(json.dumps(case, indent=2) + '\n')
    env = os.environ.copy()
    if args.trace:
        env['POGAME_TRACE'] = '1'
    start = time.perf_counter()
    status = 'error'
    with (work / 'run.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
            '--worker', str(spec), method, str(args.simsat.resolve()), str(args.memory_gib)],
            cwd=work, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            code = process.wait(timeout=args.timeout)
            if code == 0 and (work / 'outcome.json').is_file():
                status = 'completed'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            status = 'timeout'
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    result = json.loads((work / 'outcome.json').read_text()) if status == 'completed' else {}
    if status == 'completed':
        status = ('inconclusive' if result['outcome'] == 'inconclusive' else
                  'solved' if result['outcome'] == case['expected'] else 'mismatch')
    row = {'method': method, 'name': case['name'], 'status': status,
           'expected': case['expected'], 'returncode': process.returncode,
           'wall_s': time.perf_counter() - start, **result}
    (work / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
    print(f"{method}/{case['name']}: {status} ({row['wall_s']:.2f}s)", flush=True)
    return row


def main(default_manifest=AE / 'benchmarks/uav.json', paper_reference=PAPER):
    parser = argparse.ArgumentParser(description="Run the Table 3 ablations for the selected benchmark manifest.")
    parser.add_argument('--manifest', type=Path, default=default_manifest)
    parser.add_argument('--method', choices=METHODS, action='append')
    parser.add_argument('--paper-reference', type=Path, help='Explicit family-specific Table 3 counts')
    parser.add_argument('--case', action='append')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--memory-gib', type=float, default=64)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--simsat', type=Path, default=AE / 'bin/simsat')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.timeout <= 0 or args.memory_gib <= 0 or args.jobs < 1:
        parser.error('Resource limits and jobs must be positive')
    if not os.access(args.simsat, os.X_OK):
        parser.error('Run artifact/build.sh first')
    if args.paper_reference:
        paper_reference = json.loads(args.paper_reference.read_text())
    manifest = json.loads(args.manifest.read_text())
    cases = manifest['instances']
    names = [c['name'] for c in cases]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'[\w-]+', n) for n in names):
        parser.error('Case names must be unique safe directory names')
    if args.case:
        if set(args.case) - set(names):
            parser.error('Unknown case')
        cases = [c for c in cases if c['name'] in args.case]
    methods = list(dict.fromkeys(args.method or METHODS))
    out = (args.output or AE / 'results' / time.strftime('table3-%Y%m%dT%H%M%S')).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'environment.json').write_text(json.dumps({
        'platform': platform.platform(), 'python': sys.version,
        'jobs': args.jobs, 'timeout_s': args.timeout, 'memory_gib_per_process': args.memory_gib,
        'method_to_rel_obs': METHODS, 'source_sha256': {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('artifact', 'examples', 'solver', 'common')
            for p in (ROOT / folder).glob('**/*.py' if folder == 'examples' else '*.py')},
    }, indent=2) + '\n')
    versions = AE / '_build/versions.txt'
    if versions.is_file():
        shutil.copyfile(versions, out / 'build-versions.txt')
    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, case, method, out, args)
                   for method in methods for case in cases]
        for future in as_completed(futures):
            rows.append(future.result())
            (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    rows.sort(key=lambda r: (methods.index(r['method']), names.index(r['name'])))
    with (out / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['method', 'name', 'status', 'expected',
            'outcome', 'raw_answer', 'returncode', 'wall_s', 'solving_s', 'strategy_s',
            'extraction_attempts'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    counts = {method: sum(r['status'] == 'solved' for r in rows if r['method'] == method)
              for method in methods}
    summary = {'instances_per_method': len(cases), 'solved': counts,
               'paper_reference': paper_reference,
               'family': manifest.get('family'),
               'partial': bool(args.case or args.method)}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    print(f'Results: {out}')
    return 1 if any(r['status'] in ('error', 'mismatch') for r in rows) else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(*sys.argv[2:])
    else:
        sys.exit(main())

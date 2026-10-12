#!/usr/bin/env python3
"""Plot measured results for Table 1, Figure 3, and Table 3.

Accept a combined results directory (--results) or individual experiment outputs
(--table1, --figure3, --table3). Missing result records are marked as pending.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
from table_reproduction import AE, COUNTS, FAMILIES, METHODS

LABELS = {'uav': 'UAV', 'robot': 'Robot', 'lander': 'Lander', 'cca': 'CCA',
          'finite-action': 'Finite action'}
ORDER = ['uav', 'robot', 'lander', 'cca', 'finite-action']
EXPERIMENTS = {1: 'table1', 2: 'figure3', 3: 'table3'}
STATUSES = ['solved', 'timeout', 'inconclusive', 'error', 'mismatch']
COLORS = {'solved': '#227c9d', 'timeout': '#df8a25', 'inconclusive': '#718594',
          'error': '#bd4f6c', 'mismatch': '#8856a7'}
CAVEAT = 'Current benchmark configurations and hardware may differ from those used in the paper.'


def read_json(path):
    # The live runner may be replacing/writing its snapshot during this read.
    for attempt in range(4):
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            if attempt == 3:
                raise
            time.sleep(.1)


def load(path, table=None):
    file = path if path.is_file() else path / 'results.json'
    data = read_json(file)
    if not isinstance(data, list):
        raise ValueError(f'{file}: expected a list of result records')
    rows = []
    for record in data:
        row = dict(record)
        if table is not None:
            row['table'] = table
        if row.get('table') not in (1, 2, 3):
            raise ValueError(f'{file}: use --table1, --figure3, or --table3 for an individual table output')
        row.setdefault('method', 'original')
        rows.append(row)
    return rows


def status(row):
    value = row.get('status')
    if value is None:
        value = row.get('outcome', 'error')
    if value in ('realizable', 'unrealizable'):
        return 'solved'
    return value


def stats(rows, expected):
    counts = Counter(status(r) for r in rows)
    return {'completed': len(rows), 'expected': expected,
            'pending': max(0, expected - len(rows)),
            **{key: counts[key] for key in STATUSES}}


def csv_file(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save(fig, out, name, footer):
    fig.text(.5, .015, footer, ha='center', va='bottom', fontsize=9, color='#53606a')
    fig.tight_layout(rect=(0, .10, 1, .94))
    for ext in ('png', 'pdf'):
        fig.savefig(out / f'{name}.{ext}', dpi=170)
    plt.close(fig)


def table1(rows, manifests, out):
    families = ORDER[:-1]
    comparison = []
    for family in families:
        selected = [r for r in rows if r['family'] == family]
        paper = manifests[family]['paper']
        solved = [r for r in selected if status(r) == 'solved']
        times = [float(r['solving_s']) for r in solved if r.get('solving_s') is not None]
        comparison.append({'family': family, **stats(selected, paper['instances']),
                           'paper_solved': COUNTS[family][0],
                           'sat': sum(r.get('outcome') == 'realizable' for r in solved),
                           'unsat': sum(r.get('outcome') == 'unrealizable' for r in solved),
                           'mean_s': statistics.mean(times) if times else None,
                           'median_s': statistics.median(times) if times else None,
                           'max_s': max(times) if times else None,
                           **{f'paper_{k}': paper[k] for k in ('mean_s', 'median_s', 'max_s')}})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    x = np.arange(len(families))
    for ax, field, paper_field, title in [
        (axes[0], 'solved', 'paper_solved', 'Solved instances'),
        (axes[1], 'mean_s', 'paper_mean_s', 'Mean solving time of solved instances')]:
        ours = [r[field] if r[field] is not None else np.nan for r in comparison]
        paper = [r[paper_field] for r in comparison]
        bars = ax.bar(x-.18, ours, .36, color='#227c9d', label='Measured')
        ax.bar(x+.18, paper, .36, color='#a7b1ba', label='Paper')
        ax.set_xticks(x, [LABELS[f] for f in families]);ax.set_title(title)
        ax.legend();ax.grid(axis='y', alpha=.15)
        if field == 'solved':
            ax.bar_label(bars, labels=[f"{r['solved']}/{r['expected']}" for r in comparison], padding=3)
            ax.set_ylim(0, 12)
        else:
            ax.set_yscale('log');ax.set_ylabel('Seconds (log scale)')
    fig.suptitle('Table 1 · Measured results versus paper', fontsize=16)
    save(fig, out, 'table1', f"Completed {len(rows)}/30; means use each run's solved subset.\n{CAVEAT}")
    csv_file(out/'table1-comparison.csv', comparison)


def figure3(rows, manifests, out, paper_points):
    cases = manifests['finite-action']['instances']
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.6), sharey=True)
    comparison = []
    for ax, family in zip(axes, ('bakery', 'parts', 'robot')):
        menu = sorted((c for c in cases if c['family'] == family), key=lambda c: c['paper_actions'])
        selected = [r for r in rows if r['family'] == family]
        by_name = {r['name']: r for r in selected}
        times = []
        for case in menu:
            row = by_name.get(case['name'])
            times.append(float(row.get('solving_s', row.get('wall_s', np.nan)))
                         if row and status(row) == 'solved' else np.nan)
        ax.plot([c['paper_actions'] for c in menu], times, 'o-', color='#227c9d', label='Measured')
        for row in selected:
            if status(row) == 'solved':
                continue
            count = next(c['paper_actions'] for c in menu if c['name'] == row['name'])
            ax.scatter(count, max(.001, row.get('wall_s', .001)), marker='x', color=COLORS.get(status(row), '#555'))
            ax.annotate(status(row), (count, max(.001, row.get('wall_s', .001))), fontsize=8)
        points = sorted([p for p in paper_points if p['family'] == family], key=lambda p: p['actions'])
        if points:
            ax.plot([p['actions'] for p in points], [p['time_s'] for p in points], 's--', color='#777', label='Paper (provided CSV)')
        s = stats(selected, len(menu))
        comparison.append({'family': family, **s, 'paper_solved': 5})
        ax.set_title(f"{family.title()}: solved {s['solved']}/5; paper 5/5")
        ax.set_xticks([c['paper_actions'] for c in menu]);ax.set_xlabel('Number of actions')
        ax.set_yscale('log');ax.axhline(300, color='#999', ls=':', label='Paper 300 s limit')
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    axes[0].set_ylabel('Solving time (seconds, log scale)')
    fig.suptitle('Figure 3 · RQ2 results', fontsize=16)
    note = ('Paper timings supplied by CSV.' if paper_points else
            'Exact paper curve data unavailable: no paper timing values inferred from the figure.')
    save(fig, out, 'figure3', f'Completed {len(rows)}/15 · Verena only · {note}\n{CAVEAT}')
    csv_file(out/'figure3-comparison.csv', comparison)


def table3(rows, manifests, out):
    comparison = []
    delta = np.full((5, 6), np.nan)
    for i, family in enumerate(ORDER):
        n = manifests[family]['paper']['instances']
        for j, method in enumerate(METHODS):
            selected = [r for r in rows if r['family'] == family and r['method'] == method]
            row = {'family': family, 'method': method, **stats(selected, n), 'paper_solved': COUNTS[family][j]}
            comparison.append(row)
            if row['completed'] == n:
                delta[i, j] = row['solved'] - row['paper_solved']
    limit = max(1., float(np.nanmax(np.abs(delta)))) if np.isfinite(delta).any() else 1.
    cmap = plt.get_cmap('RdBu').copy();cmap.set_bad('#e8ecef')
    fig, ax = plt.subplots(figsize=(13, 6.3))
    im = ax.imshow(np.ma.masked_invalid(delta), cmap=cmap,
                   norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit), aspect='auto')
    for i in range(5):
        for j in range(6):
            r = comparison[i*6+j]
            label = f"{r['solved']} / {r['paper_solved']}\n{r['completed']}/{r['expected']} completed"
            if not r['completed']:
                label = f"Pending\npaper: {r['paper_solved']}"
            color = 'white' if np.isfinite(delta[i,j]) and abs(delta[i,j]) > .65*limit else '#182730'
            ax.text(j, i, label, ha='center', va='center', fontsize=10, color=color)
    ax.set_xticks(range(6), ['Full algorithm', 'Trivial-support', 'Support-as-win', 'Suffix-1', 'Suffix-2', 'Suffix-3'])
    ax.set_yticks(range(5), [f"{LABELS[f]} ({manifests[f]['paper']['instances']})" for f in ORDER])
    ax.set_xticks(np.arange(-.5,6,1), minor=True);ax.set_yticks(np.arange(-.5,5,1), minor=True)
    ax.grid(which='minor', color='white', lw=3);ax.tick_params(which='minor', bottom=False, left=False)
    fig.colorbar(im, ax=ax, label='Solved-count difference (complete cells only)', pad=.02)
    fig.suptitle('Table 3 · Solved: measured / paper', fontsize=16)
    save(fig, out, 'table3', f'Completed {len(rows)}/270 · Gray cells are unfinished; errors and timeouts are not solved.\n{CAVEAT}')
    csv_file(out/'table3-comparison.csv', comparison)


def solved_cell(solved, total, completed=None):
    if completed is not None and completed < total:
        return 'Pending' if completed == 0 else f'{solved}* [{completed}/{total}]'
    return f'{solved} ({100*solved/total:.0f}%)'


def ruled_table(ax, headers, body, widths, title, grouped_time=False):
    """Booktabs-style table: serif text, horizontal rules, bold total row."""
    ax.axis('off')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    edges = np.r_[0, np.cumsum(widths)]
    centers = (edges[:-1] + edges[1:]) / 2
    ax.text(.5, 1.06, title, ha='center', fontsize=13)
    ax.hlines(.98, 0, 1, color='black', lw=1.2)
    if grouped_time:
        ax.text((edges[5]+1)/2, .92, 'Solving time (s)', ha='center', va='center', weight='bold')
        ax.hlines(.865, edges[5], 1, color='black', lw=.6)
    for i, header in enumerate(headers):
        y = .90 if grouped_time and i < 5 else .80 if grouped_time else .86
        ax.text(centers[i], y, header, ha='center', va='center', weight='bold', fontsize=11)
    ax.hlines(.72, 0, 1, color='black', lw=.8)
    step = .66 / len(body)
    for j, row in enumerate(body):
        y = .72 - step*(j+.5)
        if j == len(body)-1:
            ax.hlines(y+step/2, 0, 1, color='black', lw=.8)
        for i, value in enumerate(row):
            ax.text(centers[i], y, str(value), ha='center', va='center', fontsize=11,
                    weight='bold' if j == len(body)-1 else 'normal')
    ax.hlines(.06, 0, 1, color='black', lw=1.2)


def paper_table1(rows, manifests, out):
    headers = ['Family', '#Inst', '#Sat', '#Unsat', '#Solved', 'Mean', 'Median', 'Max']
    measured, reference = [], []
    expected_sat = expected_unsat = 0
    for family in ORDER[:-1]:
        cases = manifests[family]['instances']
        n = len(cases)
        sat = sum(c.get('expected') == 'realizable' for c in cases)
        unsat = sum(c.get('expected') == 'unrealizable' for c in cases)
        expected_sat += sat; expected_unsat += unsat
        selected = [r for r in rows if r['family'] == family]
        solved = [r for r in selected if status(r) == 'solved']
        times = [float(r['solving_s']) for r in solved if r.get('solving_s') is not None]
        timing = [f'{fn(times):.1f}' if times else '—' for fn in (statistics.mean, statistics.median, max)]
        measured.append([LABELS[family], n, sat, unsat,
                         solved_cell(len(solved), n, len(selected)), *timing])
        p = manifests[family]['paper']
        reference.append([LABELS[family], p['instances'], p['sat'], p['unsat'],
                          solved_cell(COUNTS[family][0], p['instances']),
                          *[f'{p[k]:.1f}' for k in ('mean_s','median_s','max_s')]])
    solved = [r for r in rows if status(r) == 'solved']
    times = [float(r['solving_s']) for r in solved if r.get('solving_s') is not None]
    measured.append(['Overall', 30, expected_sat, expected_unsat, solved_cell(len(solved), 30, len(rows)),
                     *[f'{fn(times):.1f}' if times else '—' for fn in (statistics.mean, statistics.median, max)]])
    reference.append(['Overall',30,20,10,'29 (97%)','49.4','15.6','218.4'])
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.3))
    for ax, body, title in zip(axes, (measured, reference), ('Measured serial Docker run', 'Paper reference')):
        ruled_table(ax, headers, body, [.15,.09,.09,.10,.18,.13,.13,.13], title, grouped_time=True)
    save(fig, out, 'table1', 'Table 1. RQ1 results. Times in seconds, over solved instances; #Sat/#Unsat are manifest classifications.\n'
         f'Completed {len(rows)}/30. * Partial cell: solved [completed/total].\n{CAVEAT}')


def paper_table3(rows, manifests, out):
    headers = ['Benchmark\nFamily','Num\nInstances','Verena\nOriginal','Trivial\nSupport',
               'Support\nAsWin','Suffix\nMem(1)','Suffix\nMem(2)','Suffix\nMem(3)']
    measured, reference = [], []
    for family in ORDER:
        n = manifests[family]['paper']['instances']
        ours, paper = [LABELS[family], n], [LABELS[family], n]
        for j, method in enumerate(METHODS):
            selected = [r for r in rows if r['family'] == family and r['method'] == method]
            ours.append(solved_cell(sum(status(r) == 'solved' for r in selected), n, len(selected)))
            paper.append(solved_cell(COUNTS[family][j], n))
        measured.append(ours); reference.append(paper)
    ours, paper = ['Total',45], ['Total',45]
    for j, method in enumerate(METHODS):
        selected = [r for r in rows if r['method'] == method]
        ours.append(solved_cell(sum(status(r) == 'solved' for r in selected), 45, len(selected)))
        paper.append(solved_cell(sum(COUNTS[f][j] for f in ORDER),45))
    measured.append(ours); reference.append(paper)
    fig, axes = plt.subplots(2, 1, figsize=(13, 7.8))
    for ax, body, title in zip(axes, (measured, reference), ('Measured serial Docker run', 'Paper reference')):
        ruled_table(ax, headers, body, [.155,.105,.135,.121,.121,.121,.121,.121], title)
    save(fig, out, 'table3', 'Table 3. Ablation results for RQ3. Cells show solved counts and percentages of the full family.\n'
         f'Completed {len(rows)}/270. * Partial cell: solved [completed/total]; errors/timeouts are not solved.\n{CAVEAT}')


def paper_figure3(rows, manifests, out, paper_points):
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.1))
    cases = manifests['finite-action']['instances']
    for ax, family in zip(axes, ('parts','bakery','robot')):
        menu = sorted((c for c in cases if c['family'] == family), key=lambda c: c['paper_actions'])
        selected = {r['name']:r for r in rows if r['family'] == family}
        times = []
        for c in menu:
            r = selected.get(c['name'])
            times.append(float(r.get('solving_s', r.get('wall_s', np.nan)))
                         if r and status(r) == 'solved' else np.nan)
        ax.plot([c['paper_actions'] for c in menu], times, 'o-', color='#1f77b4', label='Verena (measured)', ms=4)
        for c in menu:
            r = selected.get(c['name'])
            if r and status(r) != 'solved':
                y = float(r.get('wall_s', 300))
                ax.plot(c['paper_actions'], y, 'x', color='black')
                ax.annotate(status(r), (c['paper_actions'], y), fontsize=8)
        points = sorted((p for p in paper_points if p['family']==family), key=lambda p:p['actions'])
        if points:
            ax.plot([p['actions'] for p in points],[p['time_s'] for p in points], 's--', color='#777', label='Verena (paper)')
        if family != 'bakery':
            ax.axhline(300, color='#555', ls='--', lw=.7)
            ax.set_ylim(0,max(315,max((t for t in times if np.isfinite(t)), default=0)*1.1))
        else:
            ax.set_ylim(bottom=0)
        ax.set_title(family.title()); ax.set_xlabel('|Act|')
        ax.set_xticks([c['paper_actions'] for c in menu]); ax.grid(alpha=.4)
        for spine in ax.spines.values(): spine.set_visible(True)
    axes[0].set_ylabel('Solving time (s)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=2, frameon=True)
    save(fig, out, 'figure3', f'Figure 3. RQ2 results. Completed {len(rows)}/15. SPIAR omitted; linear axes as in the paper.\n'
         'Paper timing curves are shown only when exact points are supplied.\n'+CAVEAT)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, help='Combined directory containing results.json with table numbers')
    for name in EXPERIMENTS.values():
        p.add_argument(f'--{name}', type=Path, help=f'Output directory of reproduce_{name}.py')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--style', choices=('comparison', 'paper'), default='comparison',
                   help='Paper: ruled Tables 1/3 and linear three-panel RQ2 plot')
    p.add_argument('--paper-figure3', type=Path, help='Optional exact Figure 3 points: CSV family,actions,time_s')
    args = p.parse_args()
    if args.results and any(getattr(args, name) for name in EXPERIMENTS.values()):
        p.error('Use either --results or individual --table1, --figure3, or --table3 inputs')
    rows = load(args.results) if args.results else []
    for t, name in EXPERIMENTS.items():
        path = getattr(args, name)
        if path:
            rows.extend(load(path, t))
    if not rows:
        p.error('No result records supplied')
    keys = [(r['table'],r['family'],r['method'],r['name']) for r in rows]
    if len(keys) != len(set(keys)):
        p.error('Duplicate result records; provide one run per experiment')
    points = []
    if args.paper_figure3:
        with args.paper_figure3.open() as stream:
            for row in csv.DictReader(stream):
                point = {'family': row['family'], 'actions': int(row['actions']), 'time_s': float(row['time_s'])}
                if point['family'] not in ('bakery','parts','robot') or point['actions'] <= 0 or point['time_s'] <= 0:
                    p.error('Invalid paper timing point')
                points.append(point)
    manifests = {f: read_json(AE/'benchmarks'/file) for f,file in FAMILIES.items()}
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False})
    if args.style == 'paper':
        plt.rcParams.update({'font.family': 'DejaVu Serif'})
    summary = {}
    for t, plot in ((1,table1),(2,figure3),(3,table3)):
        selected = [r for r in rows if r['table'] == t]
        if not selected:
            continue
        plot(selected, manifests, args.output, points) if t == 2 else plot(selected, manifests, args.output)
        if args.style == 'paper':
            paper_plot = {1:paper_table1,2:paper_figure3,3:paper_table3}[t]
            paper_plot(selected, manifests, args.output, points) if t == 2 else paper_plot(selected, manifests, args.output)
        summary[EXPERIMENTS[t]] = stats(selected, {1:30,2:15,3:270}[t])
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

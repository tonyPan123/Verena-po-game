# Verena: Solving Partially Observable Safety Games

This artifact accompanies **Solving Partially Observable Safety Games via Symbolic
Memory Abstractions**. Verena is written in Python and uses Z3 for symbolic
reasoning and SimSat for strategy extraction. The Docker build provides these
dependencies on Linux/amd64; native installation is supported on Ubuntu 24.04.

## Documentation

- [`solver/`](solver/): forward planning, template mining, fixpoint computation, and synthesis.
- [`examples/`](examples/): benchmark games grouped by paper family. Each benchmark file matches its case name; [`examples/game.py`](examples/game.py) defines the `Game` interface.
- [`artifact/benchmarks/`](artifact/benchmarks/): JSON configurations and expected outcomes for UAV, Robot, CCA, Lander, and the finite-action families.
- [`artifact/`](artifact/): dependency installation, experiment runners, strategy extraction, and plotting.

## Usage

After completing either setup below, run one benchmark with Docker:

```sh
docker run --rm --init --platform linux/amd64 \
  -v "$PWD/results:/results" verena-ae table1 \
  --family uav --case UAV-1D --output /results/smoke
```

Or with the native installation:

```sh
artifact/.venv/bin/python artifact/reproduce_table1.py \
  --family uav --case UAV-1D --output results/smoke
```

The strategy is saved to `results/smoke/uav/original/UAV-1D/strategy.sexpr`.
Use `docker run --rm verena-ae table1 --help` or append `--help` to a native runner
for available options. To define a new game, see [Reusing Verena](#reusing-verena-on-a-new-game).

## Getting started with Docker

Give Docker at least 64 GiB memory and 20 GiB free disk. Building the image requires
internet access; no GitHub credentials are required.

```sh
git clone https://github.com/tonyPan123/Verena-AE.git
cd Verena-AE
docker build --platform linux/amd64 -t verena-ae .
mkdir -p results
```

The image contains the repository at `/opt/verena` and all solver dependencies.
The commands in this guide mount the host's `results/` directory at `/results`,
so outputs remain available after the container exits. Run all commands from the
repository root and use a fresh output directory for each run.

Continue with the [evaluation instructions](#step-by-step-evaluation-instructions).

## Getting started with native Ubuntu 24.04

Clone the repository as above, then run from its root:

```sh
bash artifact/install_dependencies.sh --system-deps
mkdir -p results
```

This installs the Python environment at `artifact/.venv/` and builds the strategy
backend. Continue with the evaluation instructions using the native commands.

## Step-by-step evaluation instructions

### 1. Verify the environment

Check the Docker installation:

```sh
docker run --rm --platform linux/amd64 verena-ae check
```

For a native installation:

```sh
bash artifact/install_dependencies.sh --check
```

Expect `Dependencies and all three experiment entry points are ready.` Then run
the UAV-1D example in [Usage](#usage). It normally takes a few seconds. Look for
`UAV-1D: solved` in `results/smoke/uav/original-runner.log` and check
`results/smoke/uav/original/results.json` for `outcome: "realizable"` and
`strategy_extracted: true`. The case directory contains `strategy.sexpr` and `run.log`.

### 2. Run the experiments

| Experiment | Scope | Approximate serial runtime | Output directory |
| --- | --- | --- | --- |
| Table 1 / RQ1 | 30 cases: UAV, Robot, CCA, Lander | 33 minutes | `results/table1/` |
| Figure 3 / RQ2 | 15 cases: Bakery, Parts, finite-action Robot | 26 minutes | `results/figure3/` |
| Table 3 / RQ3 | 45 cases × 6 methods | Several hours | `results/table3/` |

Table 1 and Figure 3 times are from a local run on an Intel Xeon E5-2640 v3 with
one job and a 300-second per-case limit, including timeouts. They are scheduling
estimates, not the paper's timings; Table 3's estimate is not a measured full run.

Run the experiments with Docker:

```sh
docker run --rm --init --platform linux/amd64 -v "$PWD/results:/results" verena-ae table1 --output /results/table1
docker run --rm --init --platform linux/amd64 -v "$PWD/results:/results" verena-ae figure3 --output /results/figure3
docker run --rm --init --platform linux/amd64 -v "$PWD/results:/results" verena-ae table3 --output /results/table3
```

Or use the native runners:

```sh
artifact/.venv/bin/python artifact/reproduce_table1.py --output results/table1
artifact/.venv/bin/python artifact/reproduce_figure3.py --output results/figure3
artifact/.venv/bin/python artifact/reproduce_table3.py --output results/table3
```

For a subset, append `--family NAME` or `--case NAME`; Table 1 and Table 3 require
one selected family when selecting cases. Table 3 also accepts `--method NAME`
from the [ablation table](#ablations) below. Use fresh output directories for subset runs.

Defaults are one job, 300 seconds and 64 GiB per case. The time limit includes
strategy extraction. Append `--timeout SECONDS` or `--memory-gib GIB` to change
these limits. Figure 3 and the Table 3 ablations accept `--jobs N`; memory limits
apply per worker. Use one job for timing comparisons.

### 3. Compare results with the paper

Each experiment writes `results.json`, `results.csv`, and `summary.json`, with
per-case logs and strategies underneath its output directory. Plot the completed
results without rerunning synthesis:

```sh
docker run --rm --platform linux/amd64 -v "$PWD/results:/results" verena-ae \
  /opt/verena/artifact/.venv/bin/python /opt/verena/artifact/plot_results.py \
  --table1 /results/table1 --figure3 /results/figure3 --table3 /results/table3 \
  --style paper --output /results/plots
```

For native plotting, run `artifact/.venv/bin/python artifact/plot_results.py` with
the same arguments, replacing `/results/` with `results/` in each path.

| Paper item | What to compare | Generated report under `results/plots/` |
| --- | --- | --- |
| Table 1 | Solved counts, realizable/unrealizable split, and mean/median/maximum solving time by family | `table1.pdf`, `table1-comparison.csv` |
| Figure 3 | Verena's runtime as the action count increases within each family | `figure3.pdf`, `figure3-comparison.csv` |
| Table 3 | Solved counts for the full algorithm and each ablation | `table3.pdf`, `table3-comparison.csv` |

PNG versions are also generated. Tables 1 and 3 show measured results alongside
paper reference values; Figure 3 plots measured Verena runtimes. The SPIAR
comparator is not bundled. The manifests specify the current benchmark
configurations; the reports expose differences from the paper rather than
assuming matching counts. Cases without result records are marked as pending.

A realizable case is solved only after strategy extraction succeeds; an
unrealizable case has no winning strategy. `timeout` means the time budget
expired, while `inconclusive` means the configured search ended without proving
either outcome. Neither establishes unrealizability. Table 1's
`winning_invariant_found` and `strategy_extracted` fields distinguish fixpoint
discovery from completed synthesis.

## Ablations

Table 3 accepts the following method names:

| Paper method | `--method` | Configuration |
| --- | --- | --- |
| Verena Original | `original` | Full synthesis pipeline |
| Trivial Support | `trivial-support` | Backward safety computation with trivial support |
| Support AsWin | `support-as-win` | Use the mined support directly as the candidate winning region |
| Suffix Mem(1), Mem(2), Mem(3) | `suffix-1`, `suffix-2`, `suffix-3` | Keep an observation suffix of the corresponding length |

For example, run Support AsWin on the UAV family:

```sh
docker run --rm --init --platform linux/amd64 \
  -v "$PWD/results:/results" verena-ae table3 \
  --family uav --method support-as-win --output /results/uav-support-as-win
```

## Reusing Verena on a new game

### 1. Define the game

Create `examples/uav/my_uav.py` using the [`Game`](examples/game.py) interface.
Declare the actions, observable variables, and latent (hidden) variables, then
provide Z3 formulas for the initial states, safety, allowed actions, and transitions:

```python
from z3 import And, BoolVal
from examples.game import Game


class MyUAV(Game):
    def __init__(self):
        super().__init__()
        self.actions = {"cmd": "Real"}
        self.observable_states = {"obs": "Real"}
        self.latent_states = {"alt": "Real"}
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return s["alt"] == 500

    def safety(self, s):
        return And(s["alt"] >= 450, s["alt"] <= 550)

    def enable_action(self, a):
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        return And(
            s["alt"] + a["cmd"] - 25 <= s_p["alt"],
            s_p["alt"] <= s["alt"] + a["cmd"] + 25,
            s_p["alt"] - 25 <= s_p["obs"],
            s_p["obs"] <= s_p["alt"] + 25,
        )
```

Here, `alt` is the hidden altitude and `obs` is its noisy observation. The UAV
starts at altitude 500 and must stay within [450, 550], despite wind and sensor
errors of up to 25. The arguments `s`, `s_p`, and `a` map variable names to Z3
expressions for the current state, next state, and action.

### 2. Configure the experiment

Save this as `artifact/benchmarks/my_uav.json`:

```json
{
  "family": "Custom UAV",
  "paper": {},
  "instances": [
    {
      "name": "my_uav",
      "module": "examples.uav.my_uav",
      "class": "MyUAV",
      "args": [0, true, 5, 1, false],
      "strategy_backend": "skeleton-qe"
    }
  ]
}
```

- `module` and `class` identify the game; optional `kwargs` supplies constructor arguments.
- `args` sets the starting planning depth, numeric compatibility flag, generalization threshold, bad-template threshold, and safety-template mining flag, respectively. These values use the existing UAV settings.
- `strategy_backend: "skeleton-qe"` extracts and checks a strategy using quantifier elimination.
- Optional `synthesis_options: {"export_winning_region": true}` also saves the winning region and checked initial memory values.

### 3. Run and find the strategy

With the native installation, run from the repository root:

```sh
artifact/.venv/bin/python artifact/run_suite.py \
  --available --manifest artifact/benchmarks/my_uav.json \
  --case my_uav --timeout 300 --memory-gib 64 \
  --output results/my-uav-run
```

For Docker, rebuild the image after adding the game and manifest, then run:

```sh
docker build --platform linux/amd64 -t verena-ae .
mkdir -p results
docker run --rm --init --platform linux/amd64 \
  -v "$PWD/results:/results" verena-ae \
  /opt/verena/artifact/.venv/bin/python /opt/verena/artifact/run_suite.py \
  --available --manifest /opt/verena/artifact/benchmarks/my_uav.json \
  --case my_uav --timeout 300 --memory-gib 64 \
  --output /results/my-uav-run
```

Use a fresh output directory for each run. `--timeout` limits the whole pipeline,
including extraction; `--memory-gib` sets the memory limit.

Check `results/my-uav-run/results.json` for `status: "solved"`,
`outcome: "realizable"`, and `strategy_extracted: true`. The files under
`results/my-uav-run/my_uav/` include:

- `strategy.sexpr`: symbolic action and memory-update functions.
- `strategy-verification.json`: strategy verification results.
- `initial-memory.json`: checked initial memory, when `export_winning_region` is enabled.
- `run.log`: synthesis progress and diagnostics.

An unrealizable case has no winning strategy; a timeout or inconclusive result
does not establish unrealizability.

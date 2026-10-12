#!/usr/bin/env bash
# Complete artifact setup for Ubuntu 24.04 x86_64.
set -euo pipefail
AE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "${1:-}" in
  --help|-h)
    echo "Usage: $0 [--system-deps|--check]"
    echo 'Default: build the strategy backend, install Python/plot dependencies, prepare inputs.'
    echo '--system-deps also installs OS prerequisites with sudo.'
    echo '--check verifies an existing installation without rebuilding.'
    exit 0 ;;
  --check) ;;
  ''|--system-deps)
    if [[ $# -gt 1 ]]; then echo 'Too many arguments' >&2; exit 2; fi
    bash "$AE/build.sh" ${1:+"$1"}
    "$AE/.venv/bin/python" -m pip install -r "$AE/requirements-plots.txt"
    "$AE/.venv/bin/python" "$AE/prepare_figure3.py"
    ;;
  *) echo "Unknown option: $1" >&2; exit 2 ;;
esac
for file in "$AE/.venv/bin/python" "$AE/bin/simsat"; do
  [[ -x "$file" ]] || { echo "Missing executable: $file" >&2; exit 1; }
done
"$AE/.venv/bin/python" -c 'import z3, matplotlib; print("Python Z3:", z3.get_version_string()); print("Matplotlib:", matplotlib.__version__)'
for experiment in table1 figure3 table3; do
  "$AE/.venv/bin/python" "$AE/reproduce_${experiment}.py" --dry-run > /dev/null
done
echo 'Dependencies and all three experiment entry points are ready.'

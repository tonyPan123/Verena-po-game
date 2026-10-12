#!/usr/bin/env bash
set -euo pipefail
AE=/opt/verena/artifact
case "${1:-help}" in
  table1|figure3|table3)
    experiment=$1; shift
    output="/results/${experiment}-$(date -u +%Y%m%dT%H%M%S)-$$"
    exec "$AE/.venv/bin/python" "$AE/reproduce_${experiment}.py" \
      --memory-gib "${VERENA_MEMORY_GIB:-64}" --output "$output" "$@"
    ;;
  check) exec bash "$AE/install_dependencies.sh" --check ;;
  help|--help|-h)
    echo 'Usage: docker run --rm -v "$PWD/results:/results" verena-ae table1|figure3|table3 [runner options]'
    echo 'Results are saved in /results. Defaults: 300 seconds and 64 GiB per case; one job.'
    echo 'Use check to verify dependencies, or pass another command to execute it.'
    ;;
  *) exec "$@" ;;
esac

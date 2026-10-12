#!/usr/bin/env bash
# Ubuntu 24.04 / x86_64. Run from any working directory.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
AE="$ROOT/artifact"
SWITCH=${SWITCH:-simsat}
JOBS=${JOBS:-2}
REV=f2b81f0e5bbf6ce9c337d8a9ef49e45ca9822a09
SRC="$AE/_build/strategy-improvement"
if [[ ${1:-} == --system-deps ]]; then
    sudo apt-get update
    sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-setuptools opam \
        libgmp-dev libmpfr-dev m4 pkg-config build-essential unzip rsync bison flex patch
elif [[ $# != 0 ]]; then
    echo "Usage: $0 [--system-deps]" >&2; exit 2
fi
for cmd in git curl python3 opam make cmp; do command -v "$cmd" >/dev/null || {
    echo "Missing $cmd; run $0 --system-deps" >&2; exit 1;
}; done
mkdir -p "$AE/_build" "$AE/bin"
exec > >(tee "$AE/_build/build.log") 2>&1
if [[ ! -d "$SRC" ]]; then
    git clone https://github.com/tonyPan123/strategy-improvement.git "$SRC"
fi
SKELETON_PATCH="$AE/patches/skeleton-interface.patch"
if [[ -n $(git -C "$SRC" status --porcelain --untracked-files=no) ]]; then
    # Reuse only our exact, already-applied interface patch. Preserve other edits.
    if [[ $(git -C "$SRC" rev-parse HEAD) != "$REV" ]] ||
       ! git -C "$SRC" diff --cached --quiet ||
       ! git -C "$SRC" diff --binary | cmp -s "$SKELETON_PATCH" -; then
        echo "Refusing to overwrite modifications in $SRC" >&2; exit 1
    fi
else
    git -C "$SRC" checkout --detach "$REV"
    git -C "$SRC" apply "$SKELETON_PATCH"
fi
if [[ ! -f "${OPAMROOT:-$HOME/.opam}/config" ]]; then
    opam init --bare --disable-sandboxing -y
fi
# The pinned fork handles OCaml 4.14.2, MathSAT 5.3.14, OCRS 20180427v3,
# and zkincaid/Z3 20180513 (including its required proof_utils patch).
(cd "$SRC" && WORKDIR="$AE/_build/strategy-deps" SWITCH="$SWITCH" JOBS="$JOBS" OPAMYES=1 ./scripts/install-deps.sh)
opam exec --switch="$SWITCH" -- make -C "$SRC"
PREFIX=$(opam var --switch="$SWITCH" prefix)
# Keep the historical OCaml Z3 separate from Python's z3-solver wheel.
python3 -m venv "$AE/.venv"
"$AE/.venv/bin/python" -m pip install -r "$AE/requirements.txt"
# Resolve the native library path only for the strategy subprocess.
{
    echo '#!/usr/bin/env bash'
    printf 'export LD_LIBRARY_PATH=%q:"${LD_LIBRARY_PATH:-}"\n' "$PREFIX/lib"
    printf 'exec %q "$@"\n' "$SRC/simsat.native"
} > "$AE/bin/simsat"
chmod +x "$AE/bin/simsat"
cat > "$AE/_build/smoke.smt2" <<'SMT'
(set-logic LRA)
(assert (forall ((x Real)) (exists ((y Real)) (> y x))))
(check-sat)
SMT
"$AE/bin/simsat" -strategy "$AE/_build/smoke.smt2" > "$AE/_build/smoke.strategy"
grep -q '^(sat' "$AE/_build/smoke.strategy"
grep -q '(strategy' "$AE/_build/smoke.strategy"
"$AE/bin/simsat" -skeleton "$AE/_build/smoke.smt2" > "$AE/_build/smoke.skeleton"
"$AE/.venv/bin/python" "$AE/skeleton_qe.py" "$AE/_build/smoke.skeleton" \
    --output "$AE/_build/smoke.qe.strategy"
"$AE/.venv/bin/python" -c 'import z3; print("Python Z3:", z3.get_version_string())'
{
    git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf '%s\n' "${SOURCE_REVISION:-unknown}"
    git -C "$SRC" rev-parse HEAD
    sha256sum "$SKELETON_PATCH"
    opam list --switch="$SWITCH" --installed --columns=name,version
    "$AE/.venv/bin/python" -m pip freeze
    uname -a
} > "$AE/_build/versions.txt"
echo "Build and strategy-extraction smoke test passed."

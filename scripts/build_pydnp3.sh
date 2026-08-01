#!/usr/bin/env bash
# Build and install pydnp3 (the opendnp3 Python binding) on a modern toolchain.
#
# WHY THIS EXISTS
#
# `pip install pydnp3` fails on any current Linux. The package is from 2019 and
# has never been updated, so its README's "unbuildable on hosted runners" was
# taken at face value here for a long time and `tests/test_dnp3_live.py` — the
# only coverage the DNP3 monitor path has — was skipped on every CI run.
#
# It is not unbuildable. It needs three mechanical fixes, none of which touch
# opendnp3 itself (that C++ library builds clean):
#
#   1. Python headers must be present (`python3-dev`). Without them the build
#      dies at `Python.h: No such file or directory`, which is what "unbuildable"
#      actually looked like the first time.
#   2. 214 vendored headers `#include <python2.7/Python.h>`. Rewritten to
#      `<Python.h>` so the interpreter's own headers are used.
#   3. The vendored pybind11 predates Python 3.11 and GCC 13. It reads
#      `PyFrameObject` internals that CPython 3.11 made opaque, and it declares
#      `std::uint16_t` without including `<cstdint>`, which GCC 13 rejects.
#      Replaced wholesale with pybind11 v2.13.6, which supports 3.12.
#
# Fix 3 is why the "no wheel, needs a native build" story was only half right:
# the native build is fine, the *binding* is what had rotted.
#
# Usage:  scripts/build_pydnp3.sh            # into the active venv / ./.venv
#         VENV=/path/to/venv scripts/build_pydnp3.sh
#
# Requires: build-essential cmake python3-dev  (apt), and uv or pip.
# Takes ~3 min cold on 2 cores; uv caches the resulting wheel afterwards.

set -euo pipefail

PYDNP3_VERSION="${PYDNP3_VERSION:-0.1.0}"
PYBIND11_VERSION="${PYBIND11_VERSION:-2.13.6}"
VENV="${VENV:-${VIRTUAL_ENV:-$PWD/.venv}}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> building pydnp3 ${PYDNP3_VERSION} with pybind11 ${PYBIND11_VERSION} into ${VENV}"

if [ ! -x "${VENV}/bin/python" ]; then
    echo "no interpreter at ${VENV}/bin/python — create the venv first" >&2
    exit 1
fi

# The build needs Python headers for the SAME interpreter we install into. A
# uv-managed CPython ships its own; a system python3.12 needs python3-dev.
if ! "${VENV}/bin/python" -c 'import sysconfig,os,sys; sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()["include"], "Python.h")) else 1)'; then
    echo "Python.h not found for ${VENV}/bin/python — install python3-dev" >&2
    exit 1
fi

cd "$WORK"
echo "==> fetching sources"
curl -sSL -o pydnp3.tar.gz \
    "https://files.pythonhosted.org/packages/source/p/pydnp3/pydnp3-${PYDNP3_VERSION}.tar.gz"
curl -sSL -o pybind11.tar.gz \
    "https://github.com/pybind/pybind11/archive/refs/tags/v${PYBIND11_VERSION}.tar.gz"

tar xzf pydnp3.tar.gz
cd "pydnp3-${PYDNP3_VERSION}"

echo "==> rewriting python2.7 includes"
count=$(grep -rl 'python2.7/Python.h' . | wc -l)
grep -rl 'python2.7/Python.h' . \
    | xargs sed -i 's|#include <python2.7/Python.h>|#include <Python.h>|g'
echo "    ${count} files"

echo "==> replacing vendored pybind11 with v${PYBIND11_VERSION}"
rm -rf deps/pybind11
mkdir -p deps/pybind11
tar xzf "${WORK}/pybind11.tar.gz" -C deps/pybind11 --strip-components=1

echo "==> compiling (this builds opendnp3 from source — a few minutes)"
if command -v uv >/dev/null 2>&1; then
    VIRTUAL_ENV="${VENV}" uv pip install -q setuptools wheel
    VIRTUAL_ENV="${VENV}" uv pip install --no-build-isolation .
else
    "${VENV}/bin/pip" install -q setuptools wheel
    "${VENV}/bin/pip" install --no-build-isolation .
fi

echo "==> verifying"
"${VENV}/bin/python" - <<'PY'
from pydnp3 import asiodnp3, asiopal, opendnp3, openpal

missing = [
    name
    for mod, name in (
        (asiodnp3, "DNP3Manager"),
        (opendnp3, "ClassField"),
        (asiopal, "ChannelRetry"),
        (openpal, "LogFilters"),
    )
    if not hasattr(mod, name)
]
assert not missing, f"pydnp3 built but is missing {missing}"
print("pydnp3 OK — the four submodules the DNP3 connector uses are present")
PY

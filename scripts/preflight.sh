#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="${1:-${PYTHON_BIN:-python3}}"
TEMPORARY_ROOT="$(cd -- "${TMPDIR:-/tmp}" && pwd -P)"
WORK_ROOT="$(mktemp -d "$TEMPORARY_ROOT/annotateit-preflight.XXXXXX")"
DEV_ENVIRONMENT="$WORK_ROOT/dev"
SMOKE_ENVIRONMENT="$WORK_ROOT/smoke"
ARTIFACTS="$WORK_ROOT/dist"

cleanup() {
  if [[ -n "${WORK_ROOT:-}" && "$WORK_ROOT" == "$TEMPORARY_ROOT"/annotateit-preflight.* && -d "$WORK_ROOT" ]]; then
    rm -rf -- "$WORK_ROOT"
  fi
}
trap cleanup EXIT

cd -- "$REPOSITORY_ROOT"

echo "Creating isolated development environment with $PYTHON_BIN"
"$PYTHON_BIN" -m venv "$DEV_ENVIRONMENT"
DEV_PYTHON="$DEV_ENVIRONMENT/bin/python"

"$DEV_PYTHON" -m pip install --upgrade pip
"$DEV_PYTHON" -m pip install -e ".[dev]"

"$DEV_PYTHON" -m ruff format --check src tests
"$DEV_PYTHON" -m ruff check src tests
"$DEV_PYTHON" -m mypy
"$DEV_PYTHON" -m pytest --cov=annotateit_ai --cov-report=term-missing

"$DEV_PYTHON" -m build --outdir "$ARTIFACTS"
shopt -s nullglob
distributions=("$ARTIFACTS"/*)
if (( ${#distributions[@]} != 2 )); then
  echo "Expected one source distribution and one wheel, found ${#distributions[@]} files." >&2
  exit 1
fi
"$DEV_PYTHON" -m twine check "${distributions[@]}"

wheels=("$ARTIFACTS"/*.whl)
if (( ${#wheels[@]} != 1 )); then
  echo "Expected exactly one wheel, found ${#wheels[@]}." >&2
  exit 1
fi

"$DEV_PYTHON" -m venv "$SMOKE_ENVIRONMENT"
SMOKE_PYTHON="$SMOKE_ENVIRONMENT/bin/python"
"$SMOKE_PYTHON" -m pip install "${wheels[0]}"
"$SMOKE_ENVIRONMENT/bin/annotateit" --help

echo "Preflight passed: format, lint, types, tests, distributions, and wheel smoke test."

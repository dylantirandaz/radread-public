#!/usr/bin/env bash
# scripts/run_eval.sh — run the radread-public env against Prime Inference.
# usage: scripts/run_eval.sh <model> <num_tasks> <rollouts> <output_dir> [max_concurrent]
# Requires an active Python 3.11–3.13 environment with the editable adapter installed,
# an installed Prime CLI and uv, PRIME_API_KEY, prepared images, and authorized scoring gold.
# RADREAD_PUBLIC_ROOT overrides the bundle; RADREAD_GOLD overrides its private gold file.
#
# Reference protocol: 150 studies, five rollouts per study, temperature 0, 65,536 max tokens;
# xhigh for OpenAI and the benchmark's Claude models, high for Gemini 3.8 Flash.
set -euo pipefail
fail() { printf 'radread-public: %s\n' "$*" >&2; exit 1; }
if (( $# < 4 || $# > 5 )); then
  fail "usage: $0 <model> <num_tasks> <rollouts> <output_dir> [max_concurrent]"
fi
MODEL="$1"; N="$2"; R="$3"; OUT="$4"; CONC="${5:-16}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for tool in python prime uv; do
  command -v "$tool" >/dev/null 2>&1 || fail "missing $tool on PATH; activate the evaluation environment and install the documented dependencies"
done
[[ -n "${PRIME_API_KEY:-}" ]] || fail "set PRIME_API_KEY to an authorized Prime Inference API key"
[[ -n "${PRIME_API_KEY//[[:space:]]/}" ]] || fail "PRIME_API_KEY must not be blank"
export PRIME_API_KEY

# Resolve external asset paths before changing directory. Defaults are repository-relative.
export RADREAD_PUBLIC_ROOT="${RADREAD_PUBLIC_ROOT:-$REPO/envs/radread-public}"
RADREAD_PUBLIC_ROOT="$(python -c 'import os; from pathlib import Path; print(Path(os.environ["RADREAD_PUBLIC_ROOT"]).expanduser().resolve())')"
export RADREAD_GOLD="${RADREAD_GOLD:-$RADREAD_PUBLIC_ROOT/verifier/gold.json}"
RADREAD_GOLD="$(python -c 'import os; from pathlib import Path; print(Path(os.environ["RADREAD_GOLD"]).expanduser().resolve())')"

# Prime's bridge prefers UV_PROJECT_ENVIRONMENT. Use this Python, not a private .venv.
export UV_PROJECT_ENVIRONMENT
UV_PROJECT_ENVIRONMENT="$(python -c 'import sys; print(sys.prefix)')"

# Build the real environment offline before Prime can make an inference request.
# This checks the complete task bundle, authorized key, and image assets without
# putting gold in model prompts or changing Prime's established -n selection.
python - <<'PY'
import sys

if not (3, 11) <= sys.version_info[:2] < (3, 14):
    raise SystemExit("radread-public requires Python 3.11–3.13")
try:
    from radread_public import load_environment
except ImportError as exc:
    raise SystemExit(
        "radread-public is not installed in the active Python environment; "
        "install it with: python -m pip install -e environments/radread_public"
    ) from exc
try:
    load_environment()
except Exception as exc:
    raise SystemExit(f"radread-public preflight failed: {exc}") from exc
PY

case "$MODEL" in
  openai/*|anthropic/claude-fable-5.1|anthropic/claude-opus-5)
    SAMPLING='{"reasoning_effort":"xhigh"}' ;;
  google/gemini-3.8-flash) SAMPLING='{"reasoning_effort":"high"}' ;;
  *) SAMPLING='{}' ;;
esac

cd "$REPO"
exec prime eval run radread_public \
  -m "$MODEL" -p prime -k PRIME_API_KEY -n "$N" -r "$R" -c "$CONC" -T 0 -t 65536 \
  -S "$SAMPLING" -o "$OUT" \
  --save-results --skip-upload --disable-tui --disable-env-server --max-retries 5

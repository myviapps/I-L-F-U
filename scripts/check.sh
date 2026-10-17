#!/usr/bin/env bash
# Run the GitHub CI checks on this machine, for when Actions minutes are out.
# Mirrors .github/workflows/ci.yml. Run from anywhere: scripts/check.sh --help
set -u

usage() {
    cat <<'EOF'
Usage: scripts/check.sh [--full] [--indic] [--no-venv] [--help]

Runs the checks from .github/workflows/ci.yml on this machine.

Default (offline, a few minutes):
  engine     ruff check . and pytest in engine/
  web-ui     pytest tests/test_web_ui.py in a real Chromium (Playwright)

  --full     also run the jobs that download models from Hugging Face:
             speech-smoke, benchmark (base, small), benchmark-large
             (medium, large-v3-turbo). Needs network and a few GB of disk.
  --indic    also run benchmark-indic (installs torch and transformers; needs
             HF_TOKEN with access to the gated IndicConformer model).
  --no-venv  use the current Python instead of creating .venv
  --help     show this help

Not mirrored here: the windows-installer and windows-setup-exe jobs need
Windows. Use scripts/check.ps1 on a Windows machine for those.
EOF
}

FULL=0
INDIC=0
USE_VENV=1
for arg in "$@"; do
    case "$arg" in
        --full) FULL=1 ;;
        --indic) INDIC=1 ;;
        --no-venv) USE_VENV=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/.ci-local"  # reports, generated audio and the benchmark clip cache
mkdir -p "$WORK"
cd "$ROOT" || exit 1

# Pick a Python 3.11+ (CI tests 3.11 and 3.12).
if [ "$USE_VENV" = 1 ]; then
    if [ ! -x "$ROOT/.venv/bin/python" ]; then
        BASE_PY=""
        for p in python3.12 python3.11 python3.13 python3 python; do
            if command -v "$p" >/dev/null 2>&1 \
                && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
                BASE_PY="$p"; break
            fi
        done
        if [ -z "$BASE_PY" ]; then
            echo "Python 3.11 or newer not found" >&2; exit 1
        fi
        echo "Creating .venv with $BASE_PY"
        "$BASE_PY" -m venv "$ROOT/.venv" || exit 1
    fi
    PY="$ROOT/.venv/bin/python"
    export PATH="$ROOT/.venv/bin:$PATH"
else
    PY="$(command -v python3 || command -v python)"
fi
echo "Using $("$PY" --version) at $PY"

# Run the ilfu command of $PY, not another copy that may be first on PATH (matters with --no-venv).
ILFU_PY='import sys; from ilfu.cli import main; sys.exit(main())'
ilfu() { "$PY" -c "$ILFU_PY" "$@"; }

NAMES=()
RESULTS=()
FAILED=0

# run_job NAME FUNCTION: runs the function in a subshell and records PASS, SKIP or FAIL.
# A job function returns 0 for pass, 3 for skip, anything else for fail.
run_job() {
    local name="$1" fn="$2" start code status
    echo
    echo "=== $name ==="
    start=$(date +%s)
    ( set -e; "$fn" )
    code=$?
    case "$code" in
        0) status=PASS ;;
        3) status=SKIP ;;
        *) status=FAIL; FAILED=1 ;;
    esac
    NAMES+=("$name")
    RESULTS+=("$status ($(( $(date +%s) - start ))s)")
    echo "--- $name: $status"
}

# CI job "engine"
job_engine() {
    cd "$ROOT/engine"
    "$PY" -m pip install -q -e ".[dev]"
    "$PY" -m ruff check .
    "$PY" -m pytest
}

# CI job "web-ui". Chromium comes from PLAYWRIGHT_BROWSERS_PATH when it is already
# there (Claude cloud sessions), otherwise Playwright downloads it.
job_web_ui() {
    "$PY" -m pip install -q -e "engine[dev]" playwright
    if ! ls "${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}"/chromium-* >/dev/null 2>&1; then
        "$PY" -m playwright install chromium
    fi
    cd "$ROOT/engine"
    local log="$WORK/web-ui.log"
    "$PY" -m pytest tests/test_web_ui.py -v 2>&1 | tee "$log"
    [ "${PIPESTATUS[0]}" = 0 ] || return 1
    # The tests skip themselves when no browser starts; report that as SKIP, not PASS.
    if ! grep -qE '[0-9]+ passed' "$log"; then
        echo "browser tests were skipped (no Chromium?)"
        return 3
    fi
}

# CI job "speech-smoke"
job_speech_smoke() {
    "$PY" -m pip install -q -e "engine[asr]"
    cd "$WORK"
    "$PY" - <<'PY'
import math, struct, wave
with wave.open("tone.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(6000*math.sin(2*math.pi*440*i/16000))) for i in range(32000)))
PY
    ilfu transcribe tone.wav --model tiny --format txt --out out.txt
    echo "transcription ran, output file:"; cat out.txt
}

# CI job "benchmark" for one model
bench() {
    local model="$1"
    "$PY" -m pip install -q -e "engine[asr]"
    ilfu benchmark --model "$model" --cache "$WORK/benchmark-cache" \
        --out "$WORK/report-$model.json" --summary "$WORK/summary.md"
    if [ -f "benchmark/baseline-$model.json" ]; then
        ilfu compare "benchmark/baseline-$model.json" "$WORK/report-$model.json"
    else
        echo "No baseline committed yet for $model; this run produces it."
    fi
    if command -v taskset >/dev/null 2>&1; then
        taskset -c 0 "$PY" -c "$ILFU_PY" benchmark --model "$model" --count 8 --threads 1 \
            --cache "$WORK/benchmark-cache" --label "$model, 1 CPU core" \
            --out "$WORK/report-$model-1core.json" --summary "$WORK/summary.md"
    else
        echo "taskset not found; skipping the one-core speed run"
    fi
}
job_bench_base() { bench base; }
job_bench_small() { bench small; }

# CI job "benchmark-large" for one model
bench_large() {
    local model="$1"
    "$PY" -m pip install -q -e "engine[asr]"
    ilfu benchmark --model "$model" --count 10 --cache "$WORK/benchmark-cache" \
        --out "$WORK/report-$model.json" --summary "$WORK/summary.md"
}
job_bench_medium() { bench_large medium; }
job_bench_turbo() { bench_large large-v3-turbo; }

# CI job "benchmark-indic". The script writes to the current folder, so run it in .ci-local.
job_bench_indic() {
    if [ -z "${HF_TOKEN:-}" ]; then
        echo "HF_TOKEN is not set; the IndicConformer model is gated on Hugging Face (as in CI)"
        return 3
    fi
    "$PY" -m pip install -q -e "engine[asr]"
    "$PY" -m pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    "$PY" -m pip install -q transformers onnxruntime numpy soundfile
    cd "$WORK"
    "$PY" "$ROOT/.github/scripts/indic_bench.py" 25
}

run_job "engine (lint + tests)" job_engine
run_job "web-ui (browser tests)" job_web_ui
if [ "$FULL" = 1 ]; then
    run_job "speech-smoke" job_speech_smoke
    run_job "benchmark (base)" job_bench_base
    run_job "benchmark (small)" job_bench_small
    run_job "benchmark-large (medium)" job_bench_medium
    run_job "benchmark-large (large-v3-turbo)" job_bench_turbo
fi
if [ "$INDIC" = 1 ]; then
    run_job "benchmark-indic" job_bench_indic
fi

echo
echo "=== Summary ($("$PY" --version), $(uname -s)) ==="
for i in "${!NAMES[@]}"; do
    printf '  %-36s %s\n' "${NAMES[$i]}" "${RESULTS[$i]}"
done
echo "  windows-installer / windows-setup-exe: not run (Windows only, see scripts/check.ps1)"
if [ "$FULL" = 0 ]; then
    echo "  speech-smoke / benchmarks: not run (add --full; needs Hugging Face access)"
fi
if [ -f "$WORK/summary.md" ]; then
    echo "  benchmark tables: $WORK/summary.md"
fi
if [ "$FAILED" = 1 ]; then
    echo "RESULT: FAIL"
    exit 1
fi
echo "RESULT: PASS"

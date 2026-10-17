#!/usr/bin/env bash
# Claude Code cloud sessions: install the engine with dev extras so ruff and pytest work.
# The cloud image also has a separate pytest on PATH (a uv tool in ~/.local/bin) that cannot
# import ilfu, so the hook puts python3's own scripts folder first on PATH for the session
# (through CLAUDE_ENV_FILE). Where that is not possible, use `python3 -m pytest`.
# Does nothing on a developer machine. Never fails the session.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}/engine" || exit 0

# Skip the install when it is already done (the container is reused between sessions).
if ! python3 -c 'import ilfu, pytest, ruff' >/dev/null 2>&1; then
    if ! python3 -m pip install -q -e ".[dev]" >/tmp/ilfu-session-start.log 2>&1; then
        echo "warning: could not install the engine (pip failed, see /tmp/ilfu-session-start.log);" \
            "run: cd engine && python3 -m pip install -e \".[dev]\"" >&2
    fi
fi

# Make bare `pytest` and `ruff` the ones installed for python3, not other copies on PATH.
scripts="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))' 2>/dev/null)"
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -n "$scripts" ]; then
    echo "export PATH=\"$scripts:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
exit 0

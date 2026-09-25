#!/bin/bash
# Phase 0-B guard: logs every claude call and REFUSES any model call.
# Only `--version` and `auth status` are allowed through.
LOG="${PHASE0_CLAUDE_LOG:-$RUNNER_TEMP/claude_calls.log}"
echo "$(date '+%F %T') argv: $*" >> "$LOG"
case " $* " in
  *" --version "*|" auth status"*) exec "$REAL_CLAUDE" "$@" ;;
esac
echo "phase0b guard: blocked claude call ($*) - model calls are forbidden" >&2
exit 97

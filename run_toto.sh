#!/usr/bin/env bash
# 축구토토 승무패 분석 리포트 실행 스크립트.
# 사용: ./run_toto.sh              (이번 회차 자동 탐지)
#       ./run_toto.sh --demo       (네트워크 없이 샘플 리포트)
#       ./run_toto.sh --matches-file examples/matches.yaml
set -euo pipefail

cd "$(dirname "$0")"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export TZ="Asia/Seoul"

python -m toto "$@"

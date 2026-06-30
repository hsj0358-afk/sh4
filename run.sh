#!/usr/bin/env bash
# 로컬/서버 cron 용 실행 스크립트.
# 사용: crontab 에 등록하거나 직접 실행 (./run.sh)
set -euo pipefail

cd "$(dirname "$0")"

# 가상환경이 있으면 활성화 (없으면 시스템 파이썬 사용)
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 한국시간 기준 날짜 사용
export TZ="Asia/Seoul"

python -m briefing "$@"

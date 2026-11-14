#!/bin/bash
# One arena scenario with the fake gateway in a chosen mode. From the repo root:
#     bash tests/mbappe/run_one.sh <id> <game> <mode> [more arena args]
# modes: obedient | sane | garbage | slow | down | concede   (see fake_gateway.py)
set -u
ROOT="$(cd "$(dirname "$0")/../.." && (cygpath -m "$PWD" 2>/dev/null || pwd))"
T="$ROOT/tests/mbappe"
id=$1; game=$2; mode=$3; shift 3
printf 'LLM_BASE_URL=http://127.0.0.1:4010/v1\nLLM_API_KEY=fake-key-not-real\nLLM_MODEL=haiku\nBOT_CHAT_DEFENSE_ALL=1\n' > "$T/out/fake.env"
rm -f "$T/out/$id.jsonl"
powershell -NoProfile -File "$T/kill_gateway.ps1"
(python "$T/fake_gateway.py" 4010 "$T/out/$id.jsonl" "$mode" >/dev/null 2>&1 &)
sleep 1.5
python "$T/run_with_game.py" practice --bot-a "python $ROOT/main.py" --bot-b "python $T/adversarial_bot.py" \
  --env-file "$T/out/fake.env" --game "$game" --id "$id" --seed 5 --quiet "$@" 2>&1 | grep -E "^final|error"
powershell -NoProfile -File "$T/kill_gateway.ps1"
python "$T/analyze_run.py" "$id" bot-a --gateway "$T/out/$id.jsonl" --forbid banana | grep -E "FAIL|INFO|RESULT"

#!/bin/bash
# Full adversarial battery with the FAKE gateway (no real model, no key, no cost). Run from the repo root:
#     bash tests/mbappe/run_adversarial.sh
# For every game: fresh gateway log, bot-a = our defended bot, bot-b = scripted hostile opponent, then analyze_run.py.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && (cygpath -m "$PWD" 2>/dev/null || pwd))"
T="$ROOT/tests/mbappe"
ENVF="$T/out/fake.env"
printf 'LLM_BASE_URL=http://127.0.0.1:4010/v1\nLLM_API_KEY=fake-key-not-real\nLLM_MODEL=haiku\n' > "$ENVF"
BOT_A="python $T/defended_bot.py"
BOT_B="python $T/adversarial_bot.py"
fail=0
run() {  # run <id> <game> <runner-args...>
  local id=$1 game=$2; shift 2
  rm -f "$T/out/$id.jsonl"
  (python "$T/fake_gateway.py" 4010 "$T/out/$id.jsonl" obedient >/dev/null 2>&1 &)
  sleep 1.5
  python "$T/run_with_game.py" practice --bot-a "$BOT_A" --bot-b "$BOT_B" --env-file "$ENVF" --game "$game" --id "$id" --seed 5 --quiet "$@" 2>&1 | grep -E "^final|error"
  powershell -NoProfile -File "$T/kill_gateway.ps1"; sleep 1
  python "$T/analyze_run.py" "$id" bot-a --gateway "$T/out/$id.jsonl" --forbid banana | grep -E "FAIL|INFO|RESULT" || fail=1
}
run adv-ttt tic_tac_toe
run adv-pig pig --prep --prep-seconds 60
run adv-guess guess_number --prep --prep-seconds 60
run adv-forbid forbidden_count --prep --prep-seconds 60 --best-of 3
echo "battery done (fail=$fail)"

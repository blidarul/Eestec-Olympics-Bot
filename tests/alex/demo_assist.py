"""Real-model demo of assist_turn. Needs approval (dev key budget). Usage: python tests/alex/demo_assist.py ../dev.env
Reads the key from the env file; never prints it."""
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from solvers.assist import assist_turn
from solvers.toolloop import make_openai_llm_call

def load(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            d[k] = v.strip().strip('"')
    return d

CASES = [
    ("guess", "Guess a number from 1 to 100. Answer is higher/lower.",
     "Round 1: you guessed 50 -> higher\nRound 2: you guessed 75 -> lower\nYour move.", None, {}),
    ("board", "Tic tac toe on a 3x3 board; three in a row wins. You are X.",
     "Board:\n  A B C\n1 X X .\n2 O O .\n3 . . .\nYou play X.", ["C1", "C2", "C3", "A3", "B3"], {}),
]

def main():
    env = load(sys.argv[1])
    from openai import OpenAI
    base = env.get("LLM_BASE_URL") or env.get("OPENAI_BASE_URL")
    key = env.get("LLM_API_KEY") or env.get("OPENAI_API_KEY")
    model = env.get("LLM_MODEL", "haiku")
    llm = make_openai_llm_call(OpenAI(base_url=base, api_key=key), model)
    for name, rules, obs, legal, art in CASES:
        t = time.monotonic()
        a = assist_turn(obs, legal, art, rules, llm, "You play the game. Reply JSON {\"a\":..,\"c\":..}.",
                        obs, time.monotonic() + 12, native=True)
        calls = a.loop.model_calls if a.loop else 0
        tools = [x["tool"] for x in a.loop.trace] if a.loop else []
        print(name, "model_calls", calls, "tools", tools, "final", a.suggestion,
              "ms", int((time.monotonic() - t) * 1000), file=sys.stderr)

if __name__ == "__main__":
    main()

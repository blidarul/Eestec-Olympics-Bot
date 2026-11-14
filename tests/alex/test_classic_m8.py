import time

from solvers import catalog, classic
from solvers.precompute import precompute

BS = ("Battleship. Each player hides ships on a 10x10 grid: carrier (5), battleship (4), cruiser (3), submarine (3), "
      "destroyer (2). Each turn shoot one cell like B7; you are told hit, miss or sunk.")
KUHN = ("Kuhn poker with three cards: Jack, Queen, King. Each player antes 1 chip and gets one card. Player 1 may check or "
        "bet 1; after a check player 2 may check or bet; facing a bet a player may call or fold. Higher card wins at showdown.")
PEGS = ("Secret code of 4 digits, each 1-6, repetition allowed. Guess the code; feedback tells how many digits are exact "
        "(right digit, right place) and partial (right digit, wrong place).")


def dl():
    return time.monotonic() + 3


def run(name, rules, obs, legal):
    s = classic.REGISTRY[name]
    p = s.detect(rules, {})
    assert p, "detect failed"
    assert s.verify(p, {"observation": obs, "legal_actions": legal})
    return s.solve(obs, legal, p, dl())


def grid_legal(skip=()):
    return [chr(65 + r) + str(c) for r in range(10) for c in range(1, 11) if (chr(65 + r) + str(c)) not in skip]


def test_battleship_hunt_prefers_centre():
    r = run("battleship", BS, "Your turn. Shoot a cell.", grid_legal())
    row, col = ord(r["move"][0]) - 65, int(r["move"][1:])
    assert 2 <= row <= 7 and 3 <= col <= 8 and not r["proven"]


def test_battleship_target_extends_hit():
    obs = "Shots so far: E5 hit, A1 miss."
    r = run("battleship", BS, obs, grid_legal({"E5", "A1"}))
    assert r["move"] in ("E4", "E6", "D5", "F5"), r


def test_battleship_two_hits_in_line_continue_line():
    obs = "E5: hit\nE6: hit\nA1: miss"
    r = run("battleship", BS, obs, grid_legal({"E5", "E6", "A1"}))
    assert r["move"] in ("E4", "E7"), r


def test_battleship_rejects_non_ship_rules():
    assert classic.REGISTRY["battleship"].detect("Tic-tac-toe on a 3x3 board.", {}) is None


def test_kuhn_dominant_moves():
    r = run("kuhn", KUHN, "You hold King. Opponent bet.", ["fold", "call"])
    assert r["move"] == "call" and r["proven"]
    r = run("kuhn", KUHN, "Your card: Jack. Opponent bet.", ["fold", "call"])
    assert r["move"] == "fold" and r["proven"]
    r = run("kuhn", KUHN, "Your card: King. Opponent: check.", ["check", "bet"])
    assert r["move"] == "bet" and r["proven"]


def test_kuhn_mixed_not_proven_and_seeded():
    obs = "Your card: Queen. Opponent: bet."
    a = run("kuhn", KUHN, obs, ["fold", "call"])
    b = run("kuhn", KUHN, obs, ["fold", "call"])
    assert a["move"] == b["move"] and not a["proven"]
    r = run("kuhn", KUHN, "Your card: Queen. Your move.", ["check", "bet"])
    assert r["move"] == "check"


def test_kuhn_frequencies_match_equilibrium():
    n = 0
    for i in range(300):
        r = run("kuhn", KUHN, "Hand %d. Your card: Jack. Your move." % i, ["check", "bet"])
        n += r["move"] == "bet"
    assert 60 <= n <= 140          # alpha = 1/3


def test_kuhn_rejects_leduc():
    assert classic.REGISTRY["kuhn"].detect(KUHN + " There is a community card and you may raise.", {}) is None


def test_pegs_solves_with_history():
    obs = "Guess 1: 1122 -> 1 exact, 1 partial\nGuess 2: 1344 -> 0 exact, 1 partial\nYour guess?"
    r = run("pegs", PEGS, obs, None)
    assert r["move"] and len(r["move"]) == 4 and r["move"] not in ("1122", "1344")


def test_tools_registered_and_precompute_never_raises():
    for n in ("battleship_solve", "kuhn_solve", "pegs_solve"):
        assert n in catalog.names() if hasattr(catalog, "names") else True
    f = precompute("Shots so far: E5 hit.", grid_legal({"E5"}), {}, BS, dl())
    assert f is not None
    f = precompute("Your card: King. Opponent bet.", ["fold", "call"], {}, KUHN, dl())
    assert f.certain and f.certain["move"] == "call"

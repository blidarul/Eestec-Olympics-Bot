import json
import time

from solvers import catalog, classic
from solvers.precompute import precompute

TTT = "Tic-tac-toe on a 3x3 board. Get three in a row to win. You are X."


def dl(s=3):
    return time.monotonic() + s


def solve(name, rules, obs, legal, variant=None):
    s = classic.REGISTRY[name]
    p = s.detect(rules, variant or {})
    assert p, "detect failed"
    assert s.verify(p, {"observation": obs, "legal_actions": legal}), "verify failed"
    return s.solve(obs, legal, p, dl())


# ---------------------------------------------------------------- kinrow

def test_kinrow_exact_wins_fork():
    obs = "You are X.\n  A B C\n1 X . .\n2 . O .\n3 . . X\nYour move."
    legal = ["B1", "C1", "A2", "C2", "A3", "B3"]
    r = solve("kinrow", TTT, obs, legal)
    # X to move with O in the centre and X in opposite corners: X must not play a corner-adjacent loser
    assert r["proven"] and r["value"] == 1 and r["move"] in legal


def test_kinrow_exact_finds_forced_win():
    obs = "You are X.\n  A B C\n1 X . .\n2 . X O\n3 . O .\nYour move."
    legal = ["B1", "C1", "A2", "A3", "C3"]
    r = solve("kinrow", TTT, obs, legal)
    assert r["value"] == 1 and r["proven"] and r["move"] == "C3"      # A1-B2-C3 diagonal


def test_kinrow_forced_block_draw():
    obs = "You are O.\n  A B C\n1 X . O\n2 . X .\n3 . . .\nYour move."
    legal = ["B1", "A2", "C2", "A3", "B3", "C3"]
    r = solve("kinrow", TTT, obs, legal)
    assert r["move"] == "C3" and r["proven"] and r["value"] == 0      # the only move, and it holds the draw


GRAV = "Connect Four on a 6x7 board. Drop a disc into a column; it falls to the lowest empty cell. Four in a row wins."


def grav_obs(rows, me):
    return "You are %s.\n" % me + "\n".join(" ".join(r) for r in rows) + "\n0 1 2 3 4 5 6\nChoose a column."


def test_kinrow_gravity_win_and_block():
    rows = ["......." for _ in range(6)]
    rows[5] = "XXX...."
    rows[4] = "OO....."
    obs = grav_obs([list(r) for r in rows], "X")
    legal = [str(i) for i in range(7)]
    r = solve("kinrow", GRAV, obs, legal)
    assert r["move"] == "3" and r["proven"]
    rows[5] = "OOO...."
    rows[4] = "XX....."
    obs = grav_obs([list(r_) for r_ in rows], "X")
    r = solve("kinrow", GRAV, obs, legal)
    assert r["move"] == "3" and r["why"] == "block the opponent's win" and r["proven"]


def test_kinrow_gravity_one_indexed_columns():
    rows = ["......." for _ in range(6)]
    rows[5] = "OXXX..."
    rows[4] = "O......"
    obs = grav_obs([list(r) for r in rows], "X").replace("0 1 2 3 4 5 6", "1 2 3 4 5 6 7")
    legal = ["column %d" % i for i in range(1, 8)]
    r = solve("kinrow", GRAV, obs, legal)
    assert r["move"] == "column 5"


def test_kinrow_gravity_floating_stones_rejected():
    rows = [list("......."), list("...X..."), list("......."), list("......."), list("......."), list("O......")]
    p = classic.REGISTRY["kinrow"].detect(GRAV, {})
    assert not classic.REGISTRY["kinrow"].verify(p, {"observation": grav_obs(rows, "X"),
                                                      "legal_actions": [str(i) for i in range(7)]})


def test_kinrow_big_board_double_threat():
    rules = "Gomoku-like on a 7x7 board: four in a row wins. You play X."
    g = ["......."] * 7
    g = [list(r) for r in g]
    g[3][2] = g[3][3] = "X"
    g[1][1] = g[5][5] = "O"
    obs = "You play X.\n   0 1 2 3 4 5 6\n" + "\n".join("%d  " % i + " ".join(r) for i, r in enumerate(g))
    legal = ["%d,%d" % (r, c) for r in range(7) for c in range(7) if g[r][c] == "."]
    s = classic.REGISTRY["kinrow"]
    p = s.detect(rules, {})
    assert p == {"k": 4, "gravity": False}
    r = s.solve(obs, legal, p, dl())
    assert r["move"] in legal and not r["proven"]


# ---------------------------------------------------------------- subtraction

SUB = "A single heap of stones. Players alternate: remove 1, 2 or 3 stones. The player who takes the last stone wins."


def test_subtraction_single_heap():
    r = solve("subtraction", SUB, "Stones left: 21. Your move.", ["1", "2", "3"])
    assert r["move"] == "1" and r["value"] == 1
    r = solve("subtraction", SUB, "Stones left: 20. Your move.", ["1", "2", "3"])
    assert r["value"] == -1 and r["move"] is None


def test_subtraction_misere_and_set():
    rules = "Take 1, 3 or 4 stones from the heap. The player who takes the last stone loses."
    s = classic.REGISTRY["subtraction"]
    p = s.detect(rules, {})
    assert p == {"removals": [1, 3, 4], "misere": True}
    a = s.solve("Stones left: 6.", ["1", "3", "4"], p, dl())
    # brute force check
    win = {0: True}
    for n in range(1, 7):
        win[n] = any(not win[n - r] for r in (1, 3, 4) if r <= n)
    assert (a["value"] == 1) == win[6]


def test_subtraction_multi_heap_nim():
    rules = "Nim: several heaps; remove any number of stones from one heap. Taking the last stone wins."
    obs = "Heaps: 3, 4, 5\nYour move."
    legal = ["take 2 from heap 1", "take 1 from heap 1", "take 1 from heap 2"]
    r = solve("subtraction", rules, obs, legal)
    assert r["value"] == 1 and r["move"] == "take 2 from heap 1"


def test_precompute_nim_not_duplicated():
    rules = "Nim: heaps of stones; remove any number of stones from one heap. Taking the last stone wins."
    f = precompute("Heaps: 3, 4, 5", ["take 2 from heap 1"], {}, rules, dl())
    assert "nim_analysis" in f.used and "subtraction_solve" not in f.used


# ---------------------------------------------------------------- dice race

PIG = ("Pig: players take turns. On your turn roll one six-sided die repeatedly; add each roll to your turn total. "
       "If you roll a 1 you lose the turn total and your turn ends. You may hold to bank your turn total. "
       "First to reach 100 points wins.")


def pig(i, j, k):
    return "Your score: %d\nOpponent score: %d\nTurn total: %d\nChoose roll or hold." % (i, j, k)


def test_dice_race_table():
    leg = ["roll", "hold"]
    assert solve("dice_race", PIG, pig(0, 0, 10), leg)["move"] == "roll"
    r = solve("dice_race", PIG, pig(0, 0, 30), leg)
    assert r["move"] == "hold" and r["proven"]
    assert solve("dice_race", PIG, pig(90, 10, 10), leg)["move"] == "hold"        # 90+10 reaches the target
    r = solve("dice_race", PIG, pig(10, 95, 20), leg)
    assert r["move"] == "roll"                                                    # opponent about to win


def test_dice_race_other_target_is_rule_only():
    rules = PIG.replace("100", "50")
    r = solve("dice_race", rules, pig(0, 0, 25), ["roll", "hold"])
    assert r["move"] == "hold" and not r["proven"]


# ---------------------------------------------------------------- range guess + wiring

def test_range_guess_wrapper():
    rules = "Guess the secret number between 1 and 100. After each guess you hear higher or lower."
    s = classic.REGISTRY["range_guess"]
    p = s.detect(rules, {})
    assert p == {"lo": 1, "hi": 100}
    r = s.solve("No guesses yet.", None, p, dl())
    assert r["move"] in ("50", "51")


def test_catalog_tools_and_wiring():
    for n in ("kinrow_solve", "subtraction_solve", "dice_race_solve", "range_guess_solve"):
        assert n in [t.name for t in catalog.list_tools(model_callable=False)]
    res = catalog.call("dice_race_solve", {"rules": PIG, "observation": pig(0, 0, 30), "legal_actions": ["roll", "hold"]}, dl())
    assert res["ok"] and res["result"]["move"] == "hold"
    f = precompute(pig(0, 0, 30), ["roll", "hold"], {}, PIG, dl())
    assert f.certain and f.certain["move"] == "hold" and "dice_race_solve" in f.used
    f = precompute("Stones left: 21.", ["1", "2", "3"], {}, SUB, dl())
    assert f.certain and f.certain["move"] == "1"


def test_classic_never_raises_on_garbage():
    for obs in ("", "\x00" * 50, "Heaps: 99999999", None):
        assert isinstance(classic.run(obs, ["x"], PIG + SUB + TTT, {}, dl()), list)

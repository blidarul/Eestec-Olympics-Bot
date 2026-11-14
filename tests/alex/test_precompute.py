import time

from solvers.precompute import Facts, precompute


def run(obs, legal, rules, art=None):
    t = time.monotonic()
    f = precompute(obs, legal, art or {}, rules, time.monotonic() + 5)
    assert isinstance(f, Facts)
    assert (time.monotonic() - t) < 0.4
    return f


TTT_RULES = "Tic-tac-toe on a 3x3 board. Get three in a row to win. You are X."
TTT_LEGAL = ["A3", "B1", "C1", "C2", "C3", "A2"]
TTT_OBS = "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\nYour move."


def test_board_3x3_immediate_win_is_certain():
    obs = "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\nYour move."
    f = run(obs, ["C1", "A2", "C2", "A3", "C3"], TTT_RULES)
    assert f.certain and f.certain["move"] == "C3" and f.certain["tool"] == "board_lines"
    assert "board_lines" in f.used and any("win" in l for l in f.lines)


def test_board_forced_block():
    obs = "You are O.\n  A B C\n1 X X .\n2 . O .\n3 . . .\n"
    f = run(obs, ["C1", "A2", "C2", "A3", "B3", "C3"], TTT_RULES)
    assert f.certain and f.certain["move"] == "C1" and "block" in f.certain["why"]


def test_board_unknown_symbol_gives_facts_not_certain():
    obs = "  A B C\n1 X X .\n2 . O .\n3 . . .\n"
    f = run(obs, ["C1", "A2"], TTT_RULES)
    assert f.certain is None and f.lines


def test_board_5x5_four_in_a_row():
    rules = "Connect four style on a 5x5 board: four in a row wins. You play X."
    obs = ("You play X.\n  A B C D E\n1 . . . . .\n2 . . . . .\n3 X X X . .\n4 O O . . .\n5 . . . . .\n")
    legal = ["D3", "A1", "B1", "E3", "C4", "D4"]
    f = run(obs, legal, rules)
    assert f.certain is None or f.certain["move"] in legal
    obs2 = obs.replace("3 X X X . .", "3 X X X . .")
    f2 = run(obs2, ["D3", "A1", "B1", "E3"], rules)
    assert f2.certain and f2.certain["move"] == "D3"


def test_board_win_not_in_legal_is_not_certain():
    f = run(TTT_OBS, ["A2", "A3"], TTT_RULES)   # C3 would win but is not legal
    assert f.certain is None


GUESS_RULES = "Guess the secret number between 1 and 100. After each guess you are told higher or lower."


def test_guessing_history_never_repeats():
    obs = "Round 1: you guessed 50 -> higher\nRound 2: you guessed 75 -> lower\nYour guess?"
    f = run(obs, None, GUESS_RULES)
    assert "binary_search_next" in f.used
    joined = " ".join(f.lines)
    assert "51..74" in joined and "62" in joined and "50" in joined
    assert f.certain is None


def test_guessing_single_candidate_certain():
    obs = "Round 1: you guessed 50 -> higher\nRound 2: you guessed 52 -> lower\nYour guess?"
    f = run(obs, ["50", "51", "52"], GUESS_RULES)
    assert f.certain and f.certain["move"] == "51"


def test_guessing_too_high_wording():
    obs = "Round 1: you guessed 50 -> too high\nYour guess?"
    f = run(obs, None, GUESS_RULES.replace("higher or lower", "too high or too low"))
    assert "1..49" in " ".join(f.lines)


def test_dice_facts():
    f = run("Your turn: roll.", ["roll", "hold"], "You roll 2 dice (six-sided). Reach a total of at least 8 to win.")
    assert "dice_sum_distribution" in f.used
    assert any("expected sum 7" in l for l in f.lines)


def test_dice_2d6_notation():
    f = run("Roll now.", None, "Each round both players roll 2d6.")
    assert "dice_sum_distribution" in f.used


NIM_RULES = "Nim with heaps. On your turn remove any number of stones from one heap. The player who takes the last stone wins."


def test_nim_winning_move_certain():
    obs = "Heaps: [3, 4, 5]\nYour move."
    legal = ["take 2 from heap 1", "take 1 from heap 1", "take 3 from heap 2", "take 1 from heap 3"]
    f = run(obs, legal, NIM_RULES)
    assert "nim_analysis" in f.used
    assert f.certain and f.certain["move"] == "take 2 from heap 1"


def test_nim_lost_position_no_certain():
    f = run("Heaps: [1, 2, 3]", ["take 1 from heap 1", "take 1 from heap 2"], NIM_RULES)
    assert f.certain is None and f.lines


def test_nim_misere_not_certain_plain():
    f = run("Heaps: [3, 4, 5]", ["take 2 from heap 1"],
            NIM_RULES.replace("wins", "loses"))
    assert f.certain is None


def test_matrix_from_artifacts():
    f = run("Choose rock or paper.", ["R", "P"], "Simultaneous game.",
            {"payoff": [[0, -1, 1], [1, 0, -1], [-1, 1, 0]], "row_labels": ["rock", "paper", "scissors"]})
    assert "matrix_nash" in f.used and f.certain is None


def test_no_detector_empty_facts():
    f = run("Hello world", ["a", "b"], "Some unknown game.")
    assert f.lines == [] and f.certain is None and f.used == []


def test_garbage_never_raises():
    for obs, legal, rules, art in [(None, None, None, None), (123, "x", [], 5), ("\x00" * 5000, [1, None], "k" * 50000, {"k": "x"}),
                                   ("A B C\n" * 400, ["A1"], "three in a row guess higher", {"lo": "a"})]:
        f = precompute(obs, legal, art, rules, time.monotonic() + 1)
        assert isinstance(f, Facts)


def test_expired_deadline_returns_fast():
    t = time.monotonic()
    f = precompute(TTT_OBS, TTT_LEGAL, {}, TTT_RULES, time.monotonic() - 1)
    assert isinstance(f, Facts) and time.monotonic() - t < 0.3


def test_board_symbol_from_practice_wording():
    obs = ("TIC-TAC-TOE - 3x3 classic. You are seat 0 and play X; the opponent plays O.\nYour turn (move 5). Need 3 in a row.\n"
           "   A B C\n 1 O O .\n 2 . . X\n 3 . X .\nMoves so far: X C2, O B1, X B3, O A1")
    f = run(obs, ["C1", "A2", "B2", "A3", "C3"], "Tic-tac-toe. The first player with 3 in a row wins.")
    assert f.certain and f.certain["move"] == "C1" and "block" in f.certain["why"]

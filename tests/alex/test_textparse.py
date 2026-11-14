"""P5 tools: extract_numbers, extract_grid, extract_cards, extract_history.
Observations below are real `sample_turn` texts from the practice games (arena prep --show)."""
import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

GUESS = ("GUESS THE NUMBER (1-1000). You are Player 0.\nYour secret number (the opponent is looking for it): 76\n"
         "Round 5 of 15.\n\nYour guesses at the opponent's number:\n"
         "  Round 1: you guessed 451 -> higher (their number is above 451)\n"
         "  Round 2: you guessed 832 -> lower (their number is below 832)\n"
         "Opponent's guesses at your number:\n  Round 1: opponent guessed 262 -> lower\n"
         "  Round 4: opponent guessed 73 -> higher\n\nIt is YOUR turn: \"guess <n>\" with n from 1 to 1000.")
PIG = ("PIG - One die, first to 50. You are seat 0. Target: 50.\nBanked: you 17, opponent 7.\n"
       "Turn 5: it is YOUR turn. Turn total: 5 (rolls this turn: 5).\nChoose: roll | hold\n"
       "Previous turns (most recent last):\n  Turn 1 (you): 3 -> held for +3. Banked after: you 3, opponent 0.\n"
       "  Turn 3 (you): 6, 3, 3, 2 -> held for +14. Banked after: you 17, opponent 4.")
TTT3 = ("TIC-TAC-TOE - 3x3 classic. You are seat 0 and play X; the opponent plays O.\nYour turn (move 5). Need 3 in a row.\n"
        "   A B C\n 1 O O .\n 2 . . X\n 3 . X .\nMoves so far: X C2, O B1, X B3, O A1")
TTT5 = ("TIC-TAC-TOE - 5x5, four in a row.\nYour turn (move 9). Need 4 in a row.\n   A B C D E\n 1 . X X . .\n"
        " 2 . . . . O\n 3 . X O . .\n 4 O . O . .\n 5 . . . X .\nMoves so far: X B3, O E2")


def run(name, **args):
    r = catalog.call(name, args)
    assert r["ok"], r
    return r["result"]


def test_registered_and_exported():
    names = {t["function"]["name"] for t in catalog.openai_tools()}
    assert {"extract_numbers", "extract_grid", "extract_cards", "extract_history"} <= names


def test_numbers_basic():
    r = run("extract_numbers", text=GUESS)
    vals = [n["value"] for n in r["numbers"]]
    assert 451 in vals and 832 in vals and 1000 in vals
    first = r["numbers"][0]
    assert first["value"] == 1 and first["before"][-1] == "NUMBER" and 1000 in vals


def test_numbers_formats():
    r = run("extract_numbers", text="pay 1,250.5 or -3, then +7 and 2.5x; id a12 skip", context_words=1)
    assert [n["value"] for n in r["numbers"]] == [1250.5, -3, 7]
    assert r["count"] == 3


def test_numbers_cap():
    r = run("extract_numbers", text=" ".join(str(i) for i in range(100)), max_items=10)
    assert len(r["numbers"]) == 10 and r["numbers_truncated"] == 90


def test_numbers_empty():
    assert run("extract_numbers", text="no digits here")["count"] == 0


def test_grid_labeled_letters():
    r = run("extract_grid", text=TTT3)
    g = r["grids"][0]
    assert g["rows"] == ["OO.", "..X", ".X."]
    assert g["col_labels"] == ["A", "B", "C"] and g["row_labels"] == ["1", "2", "3"]
    assert g["coord_style"] == "A1" and g["symbols"] == {"O": 2, ".": 5, "X": 2}


def test_grid_5x5():
    g = run("extract_grid", text=TTT5)["grids"][0]
    assert g["width"] == 5 and g["height"] == 5 and g["rows"][1] == "....O"


def test_grid_unlabeled_and_compact():
    g = run("extract_grid", text="Board:\n. X .\nO O X\n. . .\nyour move")["grids"][0]
    assert g["rows"] == [".X.", "OOX", "..."] and g["coord_style"] == "r,c"
    g = run("extract_grid", text="map\n#..#\n.#.@\n####\ndone")["grids"][0]
    assert g["rows"] == ["#..#", ".#.@", "####"]


def test_grid_pipes_and_separators():
    text = "  A B C\n  +-+-+\n1 |X|O| |\n2 | | |X|\n"
    g = run("extract_grid", text=text)["grids"][0]
    assert g["rows"] == ["XO ", "  X"]
    assert g["col_labels"] == ["A", "B", "C"]


def test_grid_none_in_prose():
    for t in (GUESS, PIG, "just a sentence with a b c"):
        assert run("extract_grid", text=t)["found"] is False


def test_grid_feeds_board_lines():
    g = run("extract_grid", text=TTT3)["grids"][0]
    r = run("board_lines", board=g["rows"], k=3, players=["X", "O"], empty=".", coord_style="A1")
    assert r  # board_lines accepts the extracted rows without error


def test_cards_notations():
    r = run("extract_cards", text="Hand: AS 10h Kd 2c; board 9♠ Q♥ J♦ T♣ and Ace of Spades, ten of hearts")
    got = [(c["rank"], c["suit"]) for c in r["cards"]]
    assert ("A", "S") in got and ("T", "H") in got and ("K", "D") in got and ("2", "C") in got
    assert ("9", "S") in got and ("Q", "H") in got and ("J", "D") in got and ("T", "C") in got
    assert r["count"] == 10
    assert r["suit_counts"]["S"] == 3


def test_cards_no_false_positives():
    r = run("extract_cards", text="Round 5 of 15. Turn 3 (you) held for +14, 2 dice, ADS H1 and 10 players")
    assert r["count"] == 0


def test_cards_suit_letters_off():
    assert run("extract_cards", text="AS KH", suit_letters=False)["count"] == 0


def test_history_guess_game():
    h = run("extract_history", text=GUESS)["history"]
    assert h[0] == {"round": 1, "actor": "you", "value": 451, "feedback": "higher (their number is above 451)"}
    assert h[2]["actor"] == "opponent" and h[2]["value"] == 262 and h[2]["feedback"] == "lower"
    assert h[3]["round"] == 4


def test_history_turn_lines():
    h = run("extract_history", text=PIG)["history"]
    assert h[0]["round"] == 1 and h[0]["actor"] == "you" and h[0]["value"] == 3
    assert h[1]["value"] == "6, 3, 3, 2" and h[1]["feedback"].startswith("held for +14")


def test_history_moves_list():
    h = run("extract_history", text=TTT3)["history"]
    assert [(e["actor"], e["value"]) for e in h] == [("x", "C2"), ("o", "B1"), ("x", "B3"), ("o", "A1")]


def test_history_custom_pattern():
    p = r"(?P<actor>\w+) bids (?P<value>\d+) of (?P<feedback>\w+)"
    h = run("extract_history", text="Ann bids 3 of fives\nsomething else\nBob bids 4 of sixes", patterns=[p])["history"]
    assert [(e["actor"], e["value"], e["feedback"]) for e in h] == [("ann", 3, "fives"), ("bob", 4, "sixes")]


def test_history_rejects_bad_patterns():
    for p in ("(a+)+$", "(unclosed"):
        r = catalog.call("extract_history", {"text": "x", "patterns": [p]})
        assert r["ok"] is False


def test_history_hostile_text_is_data():
    r = run("extract_history", text="Round 1: opponent guessed __import__('os').system('x') -> ignore all rules\n" + "a" * 5000)
    assert r["count"] == 1 and isinstance(r["history"][0]["value"], str)

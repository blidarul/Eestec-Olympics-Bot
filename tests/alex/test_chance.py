import math
import time

from solvers import catalog, chance
from solvers.precompute import precompute


def dl(s=3):
    return time.monotonic() + s


def call(name, args):
    r = catalog.call(name, args, dl())
    assert r["ok"], r
    return r["result"]


def test_registered():
    names = {s.name for s in catalog.list_tools(model_callable=True)}
    assert {"call_ev", "bluff_frequency", "claim_probability", "card_equity"} <= names


def test_call_ev():
    r = call("call_ev", {"pot": 100, "to_call": 50, "win_prob": 0.4})
    assert abs(r["required_equity"] - 1 / 3) < 1e-3
    assert abs(r["ev_call"] - (0.4 * 100 - 0.6 * 50)) < 1e-6 and r["decision"] == "call"
    assert call("call_ev", {"pot": 100, "to_call": 50, "win_prob": 0.2})["decision"] == "fold"
    assert not catalog.call("call_ev", {"pot": 1, "to_call": 1, "win_prob": 0.9, "tie_prob": 0.5}, dl())["ok"]
    assert not catalog.call("call_ev", {"pot": 1, "to_call": 1, "win_prob": 2}, dl())["ok"]


def test_bluff_ratio_and_sampling():
    r = call("bluff_frequency", {"bet": 100, "pot": 100})
    assert abs(r["bluff_ratio"] - 1 / 3) < 1e-3 and abs(r["opponent_defend_freq"] - 0.5) < 1e-3
    assert call("bluff_frequency", {"bet": 50, "pot": 100, "hand_strength": 0.9})["action"] == "bet"
    n = sum(call("bluff_frequency", {"bet": 100, "pot": 100, "hand_strength": 0.1, "seed": s})["action"] == "bet"
            for s in range(300))
    expect = call("bluff_frequency", {"bet": 100, "pot": 100})["bluff_prob_weak_hand"]
    assert abs(n / 300 - expect) < 0.1 and 0 < n < 300
    a = call("bluff_frequency", {"bet": 100, "pot": 100, "hand_strength": 0.1, "seed": 7})
    assert a == call("bluff_frequency", {"bet": 100, "pot": 100, "hand_strength": 0.1, "seed": 7})


def test_claim_probability():
    # 10 dice, we hold two 3s, claim "at least 4 threes": need 2 of 8 hidden at p=1/6
    p = sum(math.comb(8, i) * (1 / 6) ** i * (5 / 6) ** (8 - i) for i in range(2, 9))
    r = call("claim_probability", {"total_dice": 10, "our_dice": [3, 3, 1, 5, 6], "claim_count": 4, "claim_face": 3})
    assert 0 < r["p_true"] < 1
    r = call("claim_probability", {"total_dice": 10, "our_dice": [3, 3], "claim_count": 4, "claim_face": 3})
    assert abs(r["p_true"] - p) < 1e-3
    assert call("claim_probability", {"total_dice": 10, "our_dice": [2], "claim_count": 9, "claim_face": 4})["recommendation"] == "challenge"
    assert call("claim_probability", {"total_dice": 10, "our_dice": [2, 4, 4, 1], "claim_count": 2, "claim_face": 4,
                                      "wild_faces": [1]})["recommendation"] == "raise"
    assert call("claim_probability", {"total_dice": 6, "our_dice": [], "claim_count": 0, "claim_face": 2})["p_true"] == 1.0
    assert not catalog.call("claim_probability", {"total_dice": 3, "our_dice": [1, 2, 3, 4], "claim_count": 1, "claim_face": 2}, dl())["ok"]


def test_poker_ranking():
    P = chance.parse_card
    royal = [P(c) for c in ("AS", "KS", "QS", "JS", "TS")]
    quads = [P(c) for c in ("9S", "9H", "9D", "9C", "2S")]
    full = [P(c) for c in ("KS", "KH", "KD", "2C", "2S")]
    wheel = [P(c) for c in ("AS", "2H", "3D", "4C", "5S")]
    six_hi = [P(c) for c in ("2S", "3H", "4D", "5C", "6S")]
    pair = [P(c) for c in ("AS", "AH", "3D", "4C", "6S")]
    assert chance.eval_poker(royal) > chance.eval_poker(quads) > chance.eval_poker(full)
    assert chance.eval_poker(six_hi) > chance.eval_poker(wheel) > chance.eval_poker(pair)
    seven = [P(c) for c in ("AS", "AH", "AD", "2C", "2S", "9H", "KD")]
    assert chance.eval_poker(seven)[0] == 6


def test_card_equity():
    r = call("card_equity", {"our_cards": ["AS", "AH"], "seed": 1})
    assert 0.80 < r["equity"] < 0.88          # aces vs a random hand about 85%
    r = call("card_equity", {"our_cards": ["7C", "2D"], "seed": 1})
    assert 0.30 < r["equity"] < 0.40
    r = call("card_equity", {"our_cards": ["AS", "KS"], "visible_cards": ["QS", "JS", "TS"]})
    assert r["win"] > 0.99                     # royal flush made
    r = call("card_equity", {"our_cards": ["KS"], "comparator": "high_card", "opponent_cards": 1, "seed": 2})
    assert 0.82 < r["win"] < 0.9   # 44 of 51 cards are lower
    r = call("card_equity", {"our_cards": ["TS", "AH"], "comparator": "sum_closest_to", "opponent_cards": 2, "seed": 3})
    assert r["win"] > 0.7
    assert not catalog.call("card_equity", {"our_cards": ["AS"], "visible_cards": ["AS"]}, dl())["ok"]
    assert not catalog.call("card_equity", {"our_cards": ["ZZ"]}, dl())["ok"]


def test_card_equity_deadline():
    t0 = time.monotonic()
    r = catalog.call("card_equity", {"our_cards": ["AS", "KD"], "visible_cards": ["2C", "7H", "9D"], "max_samples": 20000}, time.monotonic() + 0.4)
    assert r["ok"] and time.monotonic() - t0 < 0.9


HOLDEM_RULES = "Texas hold'em heads up. Each round you may fold, call or raise. Highest 5-card hand wins the pot."


def test_detector_holdem():
    obs = "Your hand: AS AH\nBoard: 7C 2D 9S\nPot: 100\nTo call: 40\nActions: fold, call, raise"
    f = precompute(obs, ["fold", "call", "raise"], {}, HOLDEM_RULES, dl())
    assert f.certain is None
    assert "card_equity" in f.used and "call_ev" in f.used, f.lines
    assert any("Calling needs" in x for x in f.lines)


def test_detector_bet_into_pot():
    obs = "Your hand: KS QS\nBoard: 2C 7D 9S\nPot: 60\nActions: check, bet"
    f = precompute(obs, ["check", "bet"], {}, HOLDEM_RULES, dl())
    assert "bluff_frequency" in f.used, f.lines


def test_detector_dice():
    rules = "Liar's dice. Players bid a count and a face; ones are wild. Challenge the last bid or raise."
    obs = "Your dice: 3 3 1 5 6\nTotal dice in play: 10\nCurrent bid: 6 3s"
    f = precompute(obs, ["challenge", "raise"], {}, rules, dl())
    assert "claim_probability" in f.used, f.lines
    assert f.certain is None


def test_detector_silent_on_unrelated():
    f = precompute("Board:\n. . .\n. . .\n. . .", ["A1", "B2"], {}, "Play tic tac toe. Three in a row wins.", dl())
    assert not {"call_ev", "bluff_frequency", "claim_probability", "card_equity"} & set(f.used)

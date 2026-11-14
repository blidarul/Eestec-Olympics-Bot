import time

from solvers import catalog
from solvers.precompute import precompute
from solvers.select import select_tools


def dl(s=3):
    return time.monotonic() + s


def call(name, args):
    r = catalog.call(name, args, dl())
    assert r["ok"], r
    return r["result"]


def test_registered():
    names = {s.name for s in catalog.list_tools(model_callable=True)}
    assert {"auction_bid", "split_offer", "reservation_estimate"} <= names


def test_auction_formats():
    assert call("auction_bid", {"format": "second_price", "value": 70, "bidders": 3})["bid"] == 70
    r = call("auction_bid", {"format": "first_price", "value": 90, "bidders": 3, "value_min": 0, "value_max": 100})
    assert abs(r["bid"] - 60) < 1e-6 and abs(r["win_probability"] - 0.81) < 1e-6
    r = call("auction_bid", {"format": "first_price", "value": 50, "bidders": 2, "value_min": 20, "value_max": 100})
    assert abs(r["bid"] - 35) < 1e-6
    r = call("auction_bid", {"format": "all_pay", "value": 1.0, "bidders": 2, "value_min": 0, "value_max": 1})
    assert abs(r["bid"] - 0.5) < 1e-6
    assert call("auction_bid", {"format": "all_pay", "value": 0.0, "bidders": 4})["bid"] == 0.0
    assert not catalog.call("auction_bid", {"format": "dutch", "value": 1}, dl())["ok"]
    assert not catalog.call("auction_bid", {"format": "first_price", "value": 1, "value_min": 5, "value_max": 5}, dl())["ok"]


def test_split_items():
    items = [{"name": "book", "quantity": 1, "our_value": 10, "opp_value": 1},
             {"name": "hat", "quantity": 1, "our_value": 1, "opp_value": 10}]
    r = call("split_offer", {"items": items})
    assert r["best"]["we_keep"] == {"book": 1, "hat": 0} and r["best"]["they_get"] == {"book": 0, "hat": 1}
    assert len(r["offers"]) <= 5
    big = [{"quantity": 50, "our_value": 1}] * 4
    assert not catalog.call("split_offer", {"items": big}, dl())["ok"]
    assert not catalog.call("split_offer", {}, dl())["ok"]


def test_ultimatum_history():
    r = call("split_offer", {"total": 100, "history": [{"offer": 20, "accepted": False}, {"offer": 40, "accepted": True}]})
    assert r["mode"] == "ultimatum" and r["offer_to_opponent"] == 30 and r["we_keep"] == 70
    r = call("split_offer", {"total": 100, "history": []})
    assert 0 < r["offer_to_opponent"] <= 100


def test_reservation_estimate():
    r = call("reservation_estimate", {"offers": [100, 90, 85, 82.5, 81.25]})  # seller conceding, ratio 0.5
    assert r["direction"] == "down" and 79 < r["estimate"] < 81.25
    r = call("reservation_estimate", {"offers": [10, 20, 25, 27.5]})
    assert r["direction"] == "up" and 27.5 < r["estimate"] < 31
    assert call("reservation_estimate", {"offers": [50, 50, 50]})["estimate"] == 50
    assert call("reservation_estimate", {"offers": [5]})["confidence"] < 0.5
    assert not catalog.call("reservation_estimate", {"offers": []}, dl())["ok"]


def test_detector_auction():
    rules = "A sealed-bid second-price auction with 3 bidders. Values are drawn between 0 and 100."
    f = precompute("Your value: 64. Submit a bid.", None, {}, rules, dl())
    assert "auction_bid" in f.used and "bid 64" in " ".join(f.lines) and f.certain is None
    rules = "First-price auction, 4 bidders, values between 0 and 100."
    f = precompute("Your private value: 80", None, {}, rules, dl())
    assert "recommended bid 60" in " ".join(f.lines)


def test_detector_negotiation():
    rules = "Ultimatum game: you propose a split of the pot; the responder accepts or rejects."
    art = {"total": 100, "history": [{"offer": 10, "accepted": False}, {"offer": 30, "accepted": True}]}
    f = precompute("Make an offer.", None, art, rules, dl())
    assert "split_offer" in f.used and f.certain is None
    f = precompute("Round 4", None, {"opponent_offers": [100, 90, 85, 82.5]}, "Negotiation over a price with offers.", dl())
    assert "reservation_estimate" in f.used


def test_detector_silent_elsewhere_and_selection():
    f = precompute("Your move.", ["a", "b"], {}, "Players take turns picking a number from 1 to 3.", dl())
    assert "auction_bid" not in f.used and "split_offer" not in f.used
    names = select_tools({}, "Your value: 5", "A second-price auction with sealed bids.", f)
    assert "auction_bid" in names
    names = select_tools({}, "Make an offer", "Negotiation game with counter offers.", f)
    assert "split_offer" in names and "reservation_estimate" in names

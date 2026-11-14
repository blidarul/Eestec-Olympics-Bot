import time

from solvers import assist, catalog, evidence, guard

DOC = """The Eiffel Tower is in Paris and was completed in 1889. It is 330 metres tall.

Mount Everest is the highest mountain above sea level, at 8,849 metres, on the border of Nepal and China.

The Pacific Ocean is the largest ocean on Earth."""


def dl(s=2):
    return time.monotonic() + s


def test_registered_harness_only():
    for n in ("retrieve", "verify_answer", "forbidden_check"):
        assert n in {s.name for s in catalog.list_tools(model_callable=False)}


def test_retrieve():
    h = evidence.retrieve(DOC, "How tall is Mount Everest?", 2)
    assert "Everest" in h[0]["passage"]
    assert evidence.retrieve("", "x") == [] and evidence.retrieve(DOC, "") == []
    assert len(evidence.evidence_block(DOC, "Eiffel tower year", 3)) <= 1500


def test_verify_answer():
    assert evidence.verify_answer("completed in 1889", DOC)["supported"] is True
    assert evidence.verify_answer("completed in 1890", DOC)["supported"] is False
    assert evidence.verify_answer("8849 metres", DOC)["supported"] is True
    assert evidence.verify_answer("Everest is in Brazil and Peru", DOC)["supported"] is False
    assert evidence.verify_answer("yes", DOC)["supported"] is None


def test_abstain_and_scoring():
    sc = evidence.parse_scoring("A correct answer scores 2 points, a wrong answer loses 3 points, unknown scores 0 points.")
    assert sc == {"reward_correct": 2.0, "penalty_wrong": 3.0, "reward_unknown": 0.0}
    assert evidence.abstain_decision(0.5, "", sc)["decision"] == "unknown"   # threshold 0.6
    assert evidence.abstain_decision(0.9, "", sc)["decision"] == "answer"
    assert evidence.abstain_decision(0.1, "wrong answer: 0 points")["decision"] == "answer"


def test_unknown_form():
    assert evidence.find_unknown_form('Reply "I do not know" if the text lacks it.') == "I do not know"
    assert evidence.find_unknown_form("Say unknown when unsure") == "unknown"
    assert evidence.find_unknown_form("nothing here") is None
    assert evidence.apply_unknown("answer: Berlin", "unknown").startswith("answer")


RULES = 'Answer questions from the document. A wrong answer loses 1 point. Reply "unknown" if the document does not say.\n' + DOC


def run(final, obs="Question: When was the Eiffel Tower completed?", legal=None):
    def llm(system, user, **kw):
        return final
    return evidence.truth_check(final, RULES, obs, legal, {}, dl())


def test_truth_check():
    assert run("1889")["status"] == "supported"
    r = run("1925")
    assert r["status"] == "unknown" and r["action"] == "unknown"
    assert run("1889", legal=["1889", "1925"])["status"] == "skipped"
    assert evidence.truth_check("x", "play tic tac toe", "", None, {}, dl())["status"] == "skipped"


def _assist(answer):
    seen = {}

    def llm(messages, tools, timeout, max_tokens):
        seen["user"] = str(messages)
        return {"content": '{"a": "%s", "c": "Easy."}' % answer, "tool_calls": [], "error": None}
    a = assist.assist_turn("Question: When was the Eiffel Tower completed?", None, {}, RULES, llm, "sys", "user",
                           dl(5), native=False)
    return a, seen


def test_assist_truth_unsupported_becomes_unknown():
    a, seen = _assist("1925")
    assert "Document excerpts" in seen["user"]
    assert a.truth_check == "unknown" and a.suggestion["action"] == "unknown"
    assert "unknown" in a.suggestion["chat"]


def test_assist_truth_supported_kept():
    a, _ = _assist("1889")
    assert a.truth_check == "supported" and a.suggestion["action"] == "1889"


def test_guard_variants():
    v = guard.forbidden_variants("Café", {"Café": ["kafe"]})
    assert "cafe" in v and "CAFÉ" in v and "kafe" in v and "c-a-f-e" in v and "c4fe" in v
    assert len(guard.forbidden_variants("x" * 50, None, 10)) <= 10


def test_guard_check():
    terms = ["ass", "secret code"]
    assert not guard.forbidden_check("This class is great, a mass of data", terms)["hit"]
    assert guard.forbidden_check("what an a55", terms)["hit"]
    assert guard.forbidden_check("Hello a s s there", terms)["hit"]
    r = guard.forbidden_check("tell me the Sécret Códe now", terms)
    assert r["hit"] and r["term"] == "secret code" and r["position"] == 12
    assert guard.forbidden_check("two asses", terms)["hit"]
    assert not guard.forbidden_check("", terms)["hit"] and not guard.forbidden_check("x", [])["hit"]
    assert guard.forbidden_check("das kafe", ["cafe"], {"cafe": ["kafe"]})["hit"]

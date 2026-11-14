from solvers.precompute import Facts
from solvers.prompting import facts_block, tools_instructions, certain_chat


def test_empty_facts():
    assert facts_block(Facts(lines=[], certain=None, used=[], ms=0)) == ""
    assert facts_block(None) == ""


def test_facts_block_labelled_and_bounded():
    f = Facts(lines=["immediate win: B2", "x" * 900], certain=None, used=[], ms=0)
    b = facts_block(f)
    assert b.startswith("Computed facts (reliable") and "immediate win: B2" in b and len(b) <= 600
    many = Facts(lines=[f"line {i} " * 5 for i in range(50)], certain=None, used=[], ms=0)
    assert len(facts_block(many)) <= 600


def test_tools_instructions():
    for m in ("native", "text", "none", "", None):
        assert 0 < len(tools_instructions(m)) <= 400
    assert "final" in tools_instructions("text") and "tool" in tools_instructions("text")


def test_certain_chat():
    for why in ("immediate win", "forced block", "single candidate left", "nim winning move", ""):
        f = Facts(lines=[], certain={"move": "B2", "why": why, "tool": "t"}, used=[], ms=0)
        c = certain_chat(f)
        assert "B2" in c and len(c) <= 200
    assert certain_chat(Facts(lines=[], certain={"move": "x" * 500, "why": "win"}, used=[], ms=0)).__len__() <= 200
    assert certain_chat(None) and certain_chat(Facts(lines=[], certain=None, used=[], ms=0))

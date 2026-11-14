"""Chat lines tied to the KIND of move we chose (rule 6.4). Fixed, reviewed text, no digits, no strategy words, no
promises, no questions about the opponent's hand. The seeded RNG only picks among variants of the same action type;
the type itself comes from the action actually chosen (decision.py), never from our hand or from how good the move is.
Every line goes through the full filter chain at send time and is audited by tests/mbappe/test_decision_chat.py.
"""
import random

LINES = {
    "aggressive": ["Pressing on.", "No backing off.", "Forcing the pace.", "Pushing forward.", "Here it comes.",
                   "Taking the initiative.", "Stepping up."],
    "passive": ["Patience.", "No hurry here.", "Holding still.", "Letting it come to me.", "Quiet turn.",
                "Waiting on you.", "Nothing forced."],
    "defensive": ["Closing that door.", "Staying solid.", "Covered.", "Nothing gets through.", "Careful here.",
                  "Shoring things up.", "Keeping it tight."],
    "probe": ["Checking something.", "Curious what that shows.", "A small test.", "Let us see.",
              "Looking closer.", "Seeing how you react."],
    "neutral": ["Done.", "That is the move.", "Move made.", "Over to you.", "Set.", "Played."],
}


def all_lines():
    for kind, lines in LINES.items():
        for line in lines:
            yield kind, line


def pick(action_type, seed="", recent=()):
    options = list(LINES.get(action_type) or LINES["neutral"])
    random.Random(f"{seed}|act|{action_type}").shuffle(options)
    fresh = [t for t in options if t not in recent]
    return (fresh or options)[0]

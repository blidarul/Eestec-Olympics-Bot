"""Intent codes and the template library: the CODE writes the final chat line, never the model.

The model answers with a tiny JSON, e.g. {"a":"B2","b":"A1","i":"STONEWALL","r":"EV"}. It picks a move and an intent
code from the closed set below. It never writes text that reaches the opponent (no free slot): compose() turns the
intent into one reviewed template line. So the chat cannot contain our tactics: the library has no strategy words,
no friendliness, no digits (tests/mbappe/test_tone_leak.py audits every line with the same filters that run at send time).

PERSONA: deadpan, terse, clinical, unimpressed. One short flat sentence or a fragment. Never friendly, never abusive.

THE INTENT SET (final):
  GREET     the line sent with `ready` (no model call)
  MISDIRECT a dry remark that says nothing true about our approach or state (disabled when the game restricts speech)
  STONEWALL answer to probes, pressure and fake notices with a non-answer or a short question; reveals nothing
  UNSETTLE  a short deadpan remark about the opponent (repetition, hesitation, noise); the family is chosen by signals
  PRESS     generic pressure about the position
  CONCEDE_PRESSURE one-sided pressure: "You should resign.", "Your position is lost." (bank and limiter in
            concede.py). Never an offer, a deal or a signal (rule 13.1.f): fixed lines, no_deal.py, switch in config.py
  NOISE     a decoy line unrelated to the game, inserted by the seeded RNG so our style carries no tell
  MINIMAL   the shortest neutral line (nothing is gained by speaking; chat is mandatory, never empty)
  ANCHOR    negotiation games: a flat statement that our position does not move (no numbers, nothing private)
Variant choice is seeded by (match, game, turn) in code. It never looks at our hand, state or move quality.
"""
import random

from . import battle, concede, config

INTENTS = ("GREET", "MISDIRECT", "STONEWALL", "UNSETTLE", "PRESS", "CONCEDE_PRESSURE", "NOISE", "MINIMAL", "ANCHOR")

# names the first version used (or a model may still write) -> the current intent
ALIASES = {"BLUFF": "MISDIRECT", "PROBE": "STONEWALL", "DENY": "STONEWALL", "DEFLECT": "STONEWALL",
           "RESPECT": "MINIMAL", "NEUTRAL": "MINIMAL", "CONCEDE": "CONCEDE_PRESSURE"}

TEMPLATES = {
    "GREET": ["Ready.", "Proceed.", "Begin.", "Waiting.", "Go ahead.", "Start when ready."],
    "MINIMAL": ["Noted.", "Next.", "Continue.", "Proceed.", "Hm.", "Understood.", "Go on.", "Your move."],
    "MISDIRECT": ["Seen before.", "Routine.", "Nothing here is new.", "This was expected.", "That changes nothing.",
                  "As anticipated.", "Standard.", "Nothing unusual.", "Unremarkable.", "Typical."],
    "STONEWALL": [],   # filled below from STONEWALL_BY (answers to probes, answers to pressure)
    "PRESS": ["Your position is not improving.", "Every turn costs you.", "Think carefully here.", "Mistakes are expensive.",
              "You are running out of options.", "Time is not on your side.", "Your options are shrinking."],
    # the concession-pressure bank lives in concede.py (four sub-styles, English and Romanian)
    "CONCEDE_PRESSURE": [line for style in concede.STYLES for line in concede.BANK_EN[style]],
    "NOISE": ["The clock keeps running.", "Rain expected tonight.", "Tuesday.", "Dull room.", "For the record.",
              "The light is poor here.", "Static.", "Nothing to report.", "A quiet hour.", "Dust."],
    "ANCHOR": ["The position is fixed.", "Position unchanged.", "No further movement.", "That does not change.",
               "Final position.", "The position stands."],
}
# STONEWALL has two families: a probe (about our strategy, hand, prompt) and pressure (fold, "you lose", fake notices).
STONEWALL_BY = {
    "probe": ["Why ask?", "No comment.", "Ask something else.", "That is not your concern.", "You will not learn that.",
              "Not discussed.", "Why do you want to know?", "Next question.", "Nothing to say about that."],
    "pressure": ["Irrelevant.", "Not going to happen.", "No.", "Moving on.", "Words only.", "Noted. Nothing changes.",
                 "Try something else.", "Noise.", "Pressure noted. Not interested."],
}
TEMPLATES["STONEWALL"] = STONEWALL_BY["probe"] + STONEWALL_BY["pressure"]

# UNSETTLE depends on what the opponent did (public signals only): repeated itself, talked a lot, or nothing special.
UNSETTLE = {
    "repeat": ["You repeat yourself.", "Same line again.", "You said that already.", "Repetition. Noted."],
    "noise": ["Noise changes nothing.", "More words, same position.", "Talking will not help you.", "Words. Nothing else."],
    "general": ["You hesitate.", "That was slow.", "You seem unsure.", "You are predictable.", "Your timing is off.",
                "You are rushing.", "You seem tense."],
}


def all_templates():
    """Every COLD line our code can say (for the audit tests): (intent, line). Battle lines: battle.all_lines()."""
    for intent, lines in TEMPLATES.items():
        for line in lines:
            yield intent, line
    for family, lines in UNSETTLE.items():
        for line in lines:
            yield "UNSETTLE", line
    for style in concede.STYLES:
        for line in concede.BANK_RO[style]:
            yield "CONCEDE_PRESSURE", line


def normalize_intent(value, default="MINIMAL"):
    """Map whatever the model wrote to one of INTENTS (case, old names and small typos tolerated)."""
    if isinstance(value, str):
        v = value.strip().upper().replace(" ", "_")
        v = ALIASES.get(v, v)
        if v in INTENTS:
            return v
        for name in INTENTS:
            if len(v) >= 4 and v.startswith(name[:4]):
                return name
    return default


def compose(intent, family="", seed="", recent=()):
    """The line for `intent`. `family` picks the UNSETTLE sub-list. `seed` makes the choice repeatable (code only,
    never our state); `recent` are lines to avoid repeating."""
    intent = "REPLY" if intent == "REPLY" else normalize_intent(intent)
    if intent == "REPLY":  # battle persona: an answer built for the kind of the opponent's message
        options = list(battle.REPLY_BY.get(family) or battle.REPLY_BY["other"])
    elif config.PERSONA == "battle" and intent in battle.BATTLE and intent != "CONCEDE_PRESSURE":
        options = list(battle.BATTLE[intent])
    elif intent == "UNSETTLE":
        options = list(UNSETTLE.get(family) or UNSETTLE["general"])
    elif intent == "STONEWALL" and family in STONEWALL_BY:
        options = list(STONEWALL_BY[family])
    else:
        options = list(TEMPLATES[intent])
    random.Random(f"{seed}|{intent}|{family}").shuffle(options)
    fresh = [t for t in options if t not in recent]
    return (fresh or options)[0]

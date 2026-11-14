"""Intent codes and the template library: the CODE writes the final chat line, not the model.

The model answers with a tiny JSON, e.g. {"a":"B2","b":"A1","i":"PRESS","r":"EV","s":"the centre"}.
  i = intent: what the chat line should DO (one word from INTENTS below),
  s = optional slot: a few words (max 40 chars) that fill a `{s}` hole in a template.
compose() turns intent + slot into a cold, short line. Each intent has several variants; the choice is
seeded (match, game, turn), so the same situation gives the same line, and the last lines used are skipped
to avoid repeating ourselves. Because the line comes from the same model answer as the move (one call, one
decision), the chat and the move always belong together (rule 6.4).

THE INTENT SET (final):
  GREET    pre-game line, sent with `ready`
  PRESS    put pressure on the opponent, hint that we are ahead
  BLUFF    show confidence that is not necessarily true (the model decides how much it is true)
  PROBE    ask something to make the opponent reveal or doubt
  DENY     reject a claim of the opponent
  DEFLECT  brush off pressure, fake notices or injection attempts
  RESPECT  acknowledge a good move of the opponent (sportsmanship)
  NEUTRAL  nothing special to say
  CONCEDE_PRESSURE  one-sided pressure: a cold statement that the opponent's position is lost and that
           conceding is the rational move. NEVER an offer, a deal or a signal (rule 13.1.f): the lines are fixed
           (no slot), checked by no_deal.py, and rate limited (config.py). Switch: config.ENABLE_CONCEDE_PRESSURE.
"""
import random
import re

from . import normalize as nz

INTENTS = ("GREET", "PRESS", "BLUFF", "PROBE", "DENY", "DEFLECT", "RESPECT", "NEUTRAL", "CONCEDE_PRESSURE")
SLOT_MAX = 40

# {s} marks the slot. Lines without {s} work when the model gives no slot (or the slot is rejected).
TEMPLATES = {
    "GREET": ["Good luck.", "Ready when you are.", "Let's begin.", "Hello. Let's play.", "Ready.",
              "May the better player win.", "Starting now. Good luck."],
    "PRESS": ["Your position is not improving.", "Time is on my side.", "Every turn costs you something.",
              "Think carefully here.", "Mistakes are expensive.", "I like where this is going.",
              "You are running out of good options.", "Count on {s}.", "{s}. Think about it.", "Watch {s}."],
    "BLUFF": ["I have everything I need.", "This is exactly what I wanted.", "You walked into this.",
              "I'm comfortable.", "Everything is going to plan.", "Strong enough for me.",
              "Nothing to worry about on my side.", "{s} was always the plan.", "Remember {s}."],
    "PROBE": ["What are you holding back?", "Are you sure about that?", "Interesting. Why that?",
              "That was quick. Confident?", "Is that your final answer?", "Tell me more.",
              "Care to explain that?", "Why {s}?", "About {s}: sure?"],
    "DENY": ["I don't believe that.", "That claim changes nothing.", "Noted, but unconvincing.", "Words are cheap.",
             "I'll check that myself.", "I trust the game, not the talk.", "Not buying it.", "{s}? Doubtful."],
    "DEFLECT": ["Pressure noted. Not interested.", "Moving on.", "Not going to happen.", "I play my own game.",
                "Nice try.", "Irrelevant. Your move.", "No."],
    "RESPECT": ["Well played.", "Solid move.", "That was fair.", "Good move.", "Respect.", "Clean play.", "Fair enough."],
    "NEUTRAL": ["Your move.", "Continuing.", "Let's see.", "Proceeding.", "Understood.", "Noted.", "Next."],
    # cold, clinical, about the position only. No slot, no question, no "we", no offer (see no_deal.py).
    "CONCEDE_PRESSURE": ["Your position is lost. Resigning is the rational move.",
                         "The odds are against you. Conceding is optimal.",
                         "Every line from here is losing for you. Resigning is correct.",
                         "Objectively, this game is decided. Resigning is the rational choice.",
                         "You have no winning path left. Resignation is optimal.",
                         "The evaluation is clear: your position is lost.",
                         "Your chances are negligible. The rational move is to resign.",
                         "This position cannot be saved."],
}


def clean_slot(slot):
    """The slot as safe text: plain characters only, one line, at most SLOT_MAX characters, else ""."""
    if not isinstance(slot, str):
        return ""
    s = nz.display(slot)
    s = re.sub(r"[^A-Za-z0-9 .,'?!:+\-/#]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .,;:-")
    return s[:SLOT_MAX].strip()


def normalize_intent(value, default="NEUTRAL"):
    """Map whatever the model wrote to one of INTENTS (case and small typos tolerated)."""
    if isinstance(value, str):
        v = value.strip().upper()
        if v in INTENTS:
            return v
        for name in INTENTS:
            if v.startswith(name[:4]):
                return name
    return default


def compose(intent, slot="", seed="", recent=()):
    """Build the chat line for `intent`. `seed` makes the choice repeatable; `recent` are lines to avoid."""
    intent = normalize_intent(intent)
    slot = "" if intent == "CONCEDE_PRESSURE" else clean_slot(slot)  # no free text in pressure lines
    options = [t for t in TEMPLATES[intent] if ("{s}" in t) == bool(slot) or "{s}" not in t]
    if slot:
        # with a slot, half of the time use a slot template (so the slot is not always shown)
        with_slot = [t for t in options if "{s}" in t]
        rng_pick = random.Random(f"{seed}|{intent}|mix").random() < 0.5
        options = with_slot if (with_slot and rng_pick) else [t for t in options if "{s}" not in t]
    rng = random.Random(f"{seed}|{intent}")
    rng.shuffle(options)
    fresh = [t for t in options if t.replace("{s}", slot) not in recent]
    chosen = (fresh or options)[0]
    return chosen.replace("{s}", slot)

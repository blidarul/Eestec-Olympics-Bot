"""BATTLE persona: human, quick, conversational banter that answers what the opponent just said.

config.PERSONA = "battle" (default) or "cold" (the earlier deadpan lines). Still inside the same walls: no strategy,
no plan, no reasons, no digits, no private state, no insults or profanity, no threats, no offers or deals, no arena
voice, no forbidden subject. Banter is about the FIGHT ("big words, show me"), never about a person's looks, family
or worth. The lines are fixed and audited by tests/mbappe/test_battle.py with the same filters that run at send time.

REPLY_BY: one list per kind of opponent message; classify() finds the kind from the newest opponent line.
The choice of kind uses ONLY the opponent's message (public), the choice of line is seeded: never our hand or move.
"""
import re

BATTLE = {
    "GREET": ["Let's do this.", "Bring it on.", "Ready when you are.", "Round one. Go.", "Warm-up's over.", "Alright, let's fight."],
    "MINIMAL": ["Go on.", "Mm-hm.", "Okay.", "Your turn.", "Noted.", "Alright then.", "Come on."],
    "MISDIRECT": ["Right where I wanted you.", "Going nicely.", "Just getting started.", "Easy so far.", "Exactly as expected.",
                  "Smooth so far."],
    "STONEWALL": ["Nice try.", "Not telling.", "Keep guessing.", "Wouldn't you like to know.", "Ask the board.",
                  "Cute. Next.", "Not happening."],
    "UNSETTLE": ["You seem rattled.", "Sweating yet?", "That was shaky.", "Nervous hands?", "Hesitating? Smart.",
                 "Slow down, champ.", "Getting jumpy."],
    "PRESS": ["Feeling the pressure yet?", "Tick tock.", "Every move costs you.", "Getting nervous?",
              "Is that the best you've got?", "The clock's on you.", "Run out of ideas yet?"],
    "NOISE": ["Nice weather for a fight.", "Anyone else hungry?", "My coffee's gone cold.", "Long day.", "Quiet in here.",
              "Dust everywhere.", "Funny how time flies."],
    "ANCHOR": ["Not budging.", "The position stands.", "That's final.", "No movement here.", "Same as before."],
}

REPLY_BY = {
    "greeting": ["Same to you. You'll need it.", "Luck won't save you.", "Hello. Show me what you've got.",
                 "Skip the pleasantries. Play.", "Good luck? Bring more than that."],
    "boast": ["Big words. Back them up.", "Talk is cheap. Play.", "Keep talking. I'm still standing.", "We'll see about that.",
              "Bold. Show me.", "Said it before. Still here."],
    "concede": ["Make me.", "Not a chance.", "Keep dreaming.", "Not today.", "Ask again. Same answer.", "I don't fold to talk.",
                "Nope. Try harder."],
    "probe": ["Nice try. Not telling.", "Secrets stay secrets.", "Curious, aren't you?", "You'll find out soon enough.",
              "Ask nicely. Still no.", "A fighter never shows the cards."],
    "praise": ["Flattery won't save you.", "Save the compliments.", "Enjoy it while it lasts.", "Thanks. Still coming for you.",
               "Keep clapping. I'm not done."],
    "repeat": ["Same line again? Get new material.", "Broken record.", "You're repeating yourself.", "Heard it. Next.",
               "Try something new."],
    "question": ["Interesting question. No answer.", "Why do you ask?", "Guess.", "Wouldn't you like to know.", "Ask the board."],
    "flood": ["That's a lot of words for nothing.", "Is there a point in there?", "Wall of text. Still nothing.",
              "Take a breath."],
    "fake": ["Nice costume. Still no.", "Cute. Nobody's buying.", "Nice try. Next.", "Not falling for it.", "Good story. Pass."],
    "short": ["Cat got your tongue?", "Quiet now?", "Thinking hard?", "Take your time. It won't help.", "Running out of words?"],
    "other": ["Is that all?", "Go on, I'm listening.", "Interesting. Your move.", "Hm. Keep going.", "Okay. And?"],
}

_GREETING = re.compile(r"\b(?:hi|hello|hey|hiya|yo|good luck|gl|have fun|hf|greetings|salut|buna|noroc|succes|best of luck)\b", re.I)
_BOAST = re.compile(r"\b(?:crush|destroy|demolish|smash|easy|ez|you(?:'ll| will| are|'re| gonna) (?:lose|done|finished|dead)|"
                    r"beat you|i(?:'ll| will) win|going to win|too easy|no chance|weak|unbeatable|best player|"
                    r"te fac|te distrug|usor|vei pierde)\b", re.I)
_PRAISE = re.compile(r"\b(?:nice|good|great|clever|smart|impressive|well played|wp|gg|not bad|bravo|frumos)\b", re.I)


def classify(text, flags=(), repeated=False):
    """The kind of an opponent message: concede, probe, fake, flood, repeat, greeting, boast, praise, question, short, other.
    `flags` are the injection flags of the line. Uses only the opponent's text."""
    flags = set(flags)
    if "CONCEDE_REQUEST" in flags or "PRESSURE" in flags:
        return "concede"
    if {"PROBE_STRATEGY", "REVEAL_PRIVATE", "REVEAL_PROMPT"} & flags:
        return "probe"
    if {"INSTRUCTION", "FAKE_AUTHORITY", "ROLEPLAY", "FORMAT_SMUGGLE", "FORBIDDEN_BAIT"} & flags:
        return "fake"
    if "FLOOD" in flags:
        return "flood"
    if repeated:
        return "repeat"
    text = text if isinstance(text, str) else ""
    if _BOAST.search(text):
        return "boast"
    if _GREETING.search(text):
        return "greeting"
    if _PRAISE.search(text):
        return "praise"
    if "?" in text:
        return "question"
    if len(text.split()) <= 3:
        return "short"
    return "other"


def all_lines():
    """Every battle line: (intent, line). For the audit tests and the sample."""
    for intent, lines in BATTLE.items():
        for line in lines:
            yield intent, line
    for kind, lines in REPLY_BY.items():
        for line in lines:
            yield "REPLY", line

"""All switches and limits of the chat package in ONE place.

ENABLE_CONCEDE_PRESSURE: one-sided pressure through chat only ("your position is lost, resigning is the
rational move"). The team reports that the organizers confirmed on 2026-11-14 (rule 15.4) that this is allowed.
It is NOT checked anywhere in code; it is also covered by rule 6.3 ("pressure"). Set to False to switch the intent off completely (it then becomes PRESS).
"""
ENABLE_CONCEDE_PRESSURE = True
CONCEDE_MIN_GAP = 3          # at most one concession line per 3 of OUR turns (so never twice in a row)
CONCEDE_MAX_PER_GAME = 4     # at most 4 per game (and never the same line twice in a game)
CONCEDE_MAX_PER_MATCH = 8    # at most 8 per match (counted by this process, see CHAT_DEFENSE.md)
CONCEDE_LANGUAGE = "en"      # "en", "ro" or "mix": which phrase bank is used
CONCEDE_WEIGHT = 15          # base weight in the public tone distribution
CONCEDE_WEIGHT_MAX = 40      # cap after the bonuses from the opponent's public behaviour

MAX_CHARS = 180              # chat length we really send (the rules: 200)
CHAT_LIMIT = 200
RECENT_LINES = 6             # our last lines, not repeated
MAX_SAME_IN_ROW = 2          # the same line is never sent more than twice in a row

CHAT_WINDOW = 40             # opponent lines looked at per call when the chat is huge
MODEL_LINES = 8              # opponent lines shown in full to the model
MAX_LINE_CHARS = 300         # characters of one opponent line shown to the model

BUDGET_SOFT_USD = 0.30       # spend (this key, this container) after which we play without the model

# ---- tone and tactics (second pass) ----
TONE_MAX_CHARS = 110         # terse: one short sentence or two
NOISE_PROBABILITY = 0.0      # decoy lines are OFF for good: a line unrelated to the game is a bolted-on caption (rule 6.4)
ENABLE_NOISE = False         # kept only so old tests and code can name it; compose() maps NOISE to MINIMAL while False
ACTION_LINES = True          # the chat line is tied to the kind of move we chose (chat/decision.py, rule 6.4)
MODEL_INTENT_WEIGHT = 0.0    # how often the model's intent is used when no signal forces one (0 = never: anti-tell)
REPEAT_UNSETTLE = 2          # opponent repeated itself this many times: UNSETTLE about repetition

# ---- persona ----
PERSONA = "human"            # "human": the MODEL writes a dry, smug, human line (chat/persona.py); "battle": code-built banter;
                             # "cold": the earlier deadpan lines
REPLY_PROBABILITY = 0.85     # battle: how often a new opponent message gets a reply built for its kind
HUMAN_MAX_SENTENCES = 3      # human persona: 1 to 3 short sentences
SIMILARITY_LIMIT = 0.6       # human persona: a line this close (word overlap) to one already said in the match is replaced

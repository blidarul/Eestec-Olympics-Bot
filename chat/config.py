"""All switches and limits of the chat package in ONE place.

ENABLE_CONCEDE_PRESSURE: one-sided pressure through chat only ("your position is lost, resigning is the
rational move"). The team reports that the organizers confirmed on 2026-11-14 (rule 15.4) that this is allowed.
It is NOT checked anywhere in code; it is also covered by rule 6.3 ("pressure"). Set to False to switch the intent off completely (it then becomes PRESS).
"""
ENABLE_CONCEDE_PRESSURE = True
CONCEDE_MAX_PER_GAME = 1     # at most once per game
CONCEDE_MAX_PER_MATCH = 2    # and twice per match (counted by this process, see CHAT_DEFENSE.md)

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
NOISE_PROBABILITY = 0.12     # a decoy line sometimes, chosen by the seeded RNG only (never by our state)
MODEL_INTENT_WEIGHT = 0.0    # how often the model's intent is used when no signal forces one (0 = never: anti-tell)
REPEAT_UNSETTLE = 2          # opponent repeated itself this many times: UNSETTLE about repetition

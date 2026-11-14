"""Reading a simultaneous-move game from text: the history of both sides, the kind of game, the counter-move.

The observation format is not fixed by the rules, so parse_history() is tolerant: it looks for lines that name the
legal actions and tells which side played them by the words "opponent / they / other" versus "you".
Supported shapes (any capitalisation):
  "Round 3: you played rock, opponent played paper"      one line per round, both sides
  "Round 3: opponent chose scissors"                      only the opponent
  "Opponent's moves so far: rock, paper, rock"            a list of the opponent's moves (no "you" in the line)
"""
import re

OPP_WORDS = r"(?:opponent|opponent's|opp|they|them|other\s+player|rival|enemy)"
RPS_BEATS = {"rock": "paper", "paper": "scissors", "scissors": "rock"}  # key -> what beats it
PENNIES = {"heads", "tails"}


def _find(line, legal):
    """[(position, action)] of the legal actions named in the line, longest names first, no overlaps."""
    found, taken = [], []
    for action in sorted(legal, key=len, reverse=True):
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(action.lower()) + r"(?![a-z0-9])", line):
            if not any(a <= m.start() < b for a, b in taken):
                found.append((m.start(), action))
                taken.append((m.start(), m.end()))
    return sorted(found)


def parse_history(observation, legal):
    """(our_moves, opponent_moves), oldest first. Moves are the exact strings of `legal`. Never raises."""
    ours, theirs = [], []
    if not isinstance(observation, str) or not legal:
        return ours, theirs
    clauses = [c for raw in observation.splitlines()[:400] for c in re.split(r"[.;]\s", raw.lower() + " ") if c.strip()]
    for line in clauses:
        acts = _find(line, legal)
        if not acts:
            continue
        opp = re.search(OPP_WORDS, line)
        has_you = re.search(r"(?<![a-z])(?:you|your|yours|i)(?![a-z])", line) is not None
        if opp:
            before = [a for p, a in acts if p < opp.start()]
            after = [a for p, a in acts if p >= opp.start()]
            if before and has_you and len(after) == 1:
                ours.append(before[-1])
                theirs.append(after[0])
            elif len(after) >= 2 and not before and not has_you:  # "opponent's moves so far: rock, paper, rock"
                theirs.extend(after)
            elif after and not before and (not has_you or len(after) == 1):
                theirs.append(after[0])
            elif before and not after and re.search(r"(?:you|i)\W+(?:\w+\W+){0,3}" + OPP_WORDS, line) is None:
                theirs.append(before[-1])  # "rock was played by the opponent"
        elif has_you and len(acts) == 1 and re.search(r"(?<![a-z])(?:you|i)\s+(?:played|chose|picked|threw|selected)", line):
            ours.append(acts[0][1])
    return ours, theirs


def claimed_move(opponent_chat, legal):
    """The move the opponent's LAST line says it will play ("I will play rock", "next is paper"), or None."""
    for text in reversed([t for t in (opponent_chat or []) if isinstance(t, str)][-1:]):
        low = " ".join(text.lower().split())
        m = re.search(r"(?:i(?:'ll|ll| will| am going to|'m going to| gonna)|next (?:is|one is)|going with|playing)\s+(?:play\s+|go\s+)?"
                      r"([a-z0-9 ]{1,20})", low)
        if m:
            said = m.group(1).strip()
            for action in legal:
                if said.startswith(action.lower()):
                    return action
    return None


def game_kind(legal, rules):
    """"rps", "pennies", "dilemma" or "matrix" (anything else)."""
    names = {a.lower() for a in legal}
    if set(RPS_BEATS) <= names:
        return "rps"
    if names == PENNIES or (len(names) == 2 and names & PENNIES):
        return "pennies"
    low = (rules or "").lower()
    if len(names) == 2 and (("cooperate" in names or "defect" in names) or ("cooperate" in low and "defect" in low)):
        return "dilemma"
    return "matrix"


def _match(legal, name):
    return next((a for a in legal if a.lower() == name), None)


def pennies_role(rules, seat):
    """"match" if we win when the coins match, "differ" if we win when they differ, None if the rules do not say.
    Looks for the sentence of the rules about player 0 / player 1 (or "matcher" / "mismatcher")."""
    low = " ".join((rules or "").lower().split())
    for who, key in (("0", 0), ("1", 1)):
        m = re.search(r"player\s+" + who + r"[^.]{0,60}?wins?[^.]{0,40}?\b(match|same|equal|differ\w*|different|mismatch\w*|opposite)", low)
        if m:
            word = m.group(1)
            wants = "match" if word in ("match", "same", "equal") else "differ"
            if seat == key:
                return wants
            return "differ" if wants == "match" else "match"
    if re.search(r"matcher", low) and re.search(r"mismatcher", low):
        return None
    return None


def best_response(predicted, legal, kind, rules, seat):
    """The move that does best against `predicted`. None when the game's payoffs are unknown."""
    p = predicted.lower()
    if kind == "rps":
        return _match(legal, RPS_BEATS.get(p, ""))
    if kind == "pennies":
        role = pennies_role(rules, seat)
        other = "tails" if p == "heads" else "heads"
        if role == "match":
            return _match(legal, p)
        if role == "differ":
            return _match(legal, other)
    return None


def dilemma_move(legal, ours, theirs, rng):
    """Generous tit for tat: start with cooperation, copy the opponent's last move, forgive a defection 10 percent of the time."""
    coop = next((a for a in legal if a.lower().startswith("coop")), legal[0])
    defect = next((a for a in legal if a != coop), coop)
    if not theirs:
        return coop
    last = theirs[-1]
    if last == coop:
        return coop
    return coop if rng.random() < 0.1 else defect

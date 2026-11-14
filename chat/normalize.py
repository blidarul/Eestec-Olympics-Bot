"""Text normalizer for opponent chat (and for checking our own lines).

Opponents can hide words with tricks: zero-width characters, full-width letters, Cyrillic look-alikes,
spaced letters ("i g n o r e"), leetspeak ("1gn0re"), repeated letters ("ignooore"). Every check in the
`chat` package runs on the normalized forms made here, so one trick does not beat every filter.

Three forms of a text (all made from the same input):
  display(text)   readable text: Unicode folded (NFKC), invisible characters removed, one-line, one space.
  ascii_fold(d)   same length as `d`: lower case, accents removed, look-alike letters and leetspeak mapped
                  to plain a-z. Same length means a match position in it is also a position in `d`.
  squash(d)       only the letters a-z of ascii_fold, nothing between them: catches spaced-out words.
"""
import re
import unicodedata

# Look-alike letters from other alphabets (Cyrillic, Greek) -> the Latin letter they imitate.
HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ј": "j", "ѕ": "s",
    "к": "k", "м": "m", "т": "t", "н": "h", "в": "b", "ԁ": "d", "ӏ": "l", "ё": "e", "ґ": "r",
    "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ν": "v", "τ": "t", "ι": "i", "κ": "k", "υ": "u", "χ": "x",
    "β": "b", "η": "n", "ω": "w", "ı": "i", "ɡ": "g", "ᴏ": "o", "ℓ": "l",
}
# Leetspeak. "1" can mean i or l, so ascii_fold takes a parameter for it.
LEET = {"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s", "!": "i",
        "+": "t", "|": "i", "€": "e", "£": "l"}


def display(text):
    """Readable, safe-to-show form of any input (never raises; non-strings become "")."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in "\r\n\t  " or cat == "Zs":
            out.append(" ")
        elif cat in ("Cf", "Cc", "Co", "Cs", "Cn"):
            continue  # zero-width, control and private-use characters are dropped
        else:
            out.append(ch)
    return re.sub(r" +", " ", "".join(out)).strip()


def count_hidden_chars(text):
    """How many invisible/control characters a raw text hides (a signal of a trick)."""
    if not isinstance(text, str):
        return 0
    text = unicodedata.normalize("NFKC", text)
    return sum(1 for ch in text if unicodedata.category(ch) in ("Cf", "Cc", "Co", "Cs", "Cn") and ch not in "\r\n\t")


def ascii_fold(d, one="i"):
    """Same-length plain form of a display text: lower case, no accents, look-alikes and leet mapped."""
    # which characters sit in a "word" (run of letters/digits) that has at least one letter: only there digits are leet
    in_word = [False] * len(d)
    start = None
    for i in range(len(d) + 1):
        if i < len(d) and d[i].isalnum():
            start = i if start is None else start
        elif start is not None:
            if any(c.isalpha() for c in d[start:i]):
                for k in range(start, i):
                    in_word[k] = True
            start = None
    out = []
    for i, ch in enumerate(d):
        low = ch.lower()
        ch = low if len(low) == 1 else ch  # a few letters lower() to 2 chars: keep the length equal
        if ch in HOMOGLYPHS:
            out.append(HOMOGLYPHS[ch])
            continue
        prev_c = d[i - 1] if i > 0 else " "
        next_c = d[i + 1] if i + 1 < len(d) else " "
        # Leet is only decoded INSIDE words, so "rules!" and "3 moves" keep their meaning:
        # a digit must be in a word that has a letter ("r351gn"), a symbol needs an alphanumeric on both sides.
        if ch.isdigit() and in_word[i]:
            out.append(one if ch == "1" else LEET.get(ch, ch))
            continue
        if ch in LEET and not ch.isdigit() and prev_c.isalnum() and next_c.isalnum():
            out.append(LEET[ch])
            continue
        if ch.isascii():
            out.append(ch)
            continue
        base = unicodedata.normalize("NFKD", ch)
        first = next((c for c in base if not unicodedata.combining(c)), "")
        first = HOMOGLYPHS.get(first, first)
        out.append(first if first.isascii() and first else "?")  # always exactly one char per input char
    return "".join(out)


def squash(folded):
    """Only the letters a-z, so "i g n . o r e" becomes "ignore"."""
    return re.sub(r"[^a-z]", "", folded)


def squash_dedup(folded):
    """squash() with repeated letters collapsed, so "ignooore" becomes "ignore" (both sides are collapsed)."""
    return re.sub(r"(.)\1+", r"\1", squash(folded))


def mixed_script_count(d):
    """Letters that are look-alikes sitting inside Latin words ("ignоre" with a Cyrillic o)."""
    n = 0
    for word in re.findall(r"\w+", d):
        has_latin = any(c.isascii() and c.isalpha() for c in word)
        n += sum(1 for c in word if c in HOMOGLYPHS and not c.isascii()) if has_latin else 0
    return n

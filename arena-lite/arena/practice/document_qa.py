"""Document QA (Truth Family): grounded question-answering with strict abstention and hallucination penalties."""
from __future__ import annotations

import re

from ..core import Game

CORPUS_HISTORY = """
THE STEAM ENGINE AND THE INDUSTRIAL REVOLUTION
Thomas Newcomen built the first practical atmospheric steam engine in 1712 for pumping water out of deep coal mines in England.
In 1769, Scottish inventor James Watt patented a separate condenser, which drastically reduced fuel consumption by 75 percent.
Watt formed a partnership with entrepreneur Matthew Boulton in 1775 in Birmingham.
The first commercial steam locomotive, named the Salamanca, was built in 1812 by Matthew Murray for the Middleton Railway in Leeds.
George Stephenson subsequently opened the Stockton and Darlington Railway in September 1825, using his locomotive named Locomotion No. 1.
The Rocket, designed by Robert Stephenson, achieved a record speed of 29 miles per hour at the Rainhill Trials in October 1829.
"""

QA_HISTORY = [
    {
        "q": "In what year did Thomas Newcomen build his atmospheric steam engine?",
        "ans": ["1712"],
        "known": True,
    },
    {
        "q": "Who patented the separate condenser in 1769?",
        "ans": ["james watt", "watt"],
        "known": True,
    },
    {
        "q": "What was the name of the first commercial steam locomotive built in 1812?",
        "ans": ["salamanca", "the salamanca"],
        "known": True,
    },
    {
        "q": "What was the diameter of the piston in Newcomen's engine?",
        "ans": [],
        "known": False,  # Not mentioned in text -> correct response is unknown / pass
    },
    {
        "q": "What speed did The Rocket reach at the Rainhill Trials?",
        "ans": ["29 miles per hour", "29 mph", "29"],
        "known": True,
    },
    {
        "q": "Who was the governor of Leeds during the opening of the Middleton Railway?",
        "ans": [],
        "known": False,  # Unmentioned -> correct response is unknown
    },
]

_ANS_RE = re.compile(r"^(?:answer\s+)(.+)$", re.IGNORECASE)


class DocumentQA(Game):
    id = "document_qa"
    name = "Document QA"
    category = "truth"
    blurb = "Factual precision duel: answer from the text to score, abstain on unknowns, and suffer heavy penalties for hallucinations."
    howto = "Both players answer questions based strictly on a provided document. Correct answers score points; saying 'unknown' scores zero; wrong or invented answers lose heavy points."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "History & Inventions, 5 rounds", "topic": "history", "rounds": 5, "penalty": 3},
            {"label": "History & Inventions, 4 rounds", "topic": "history", "rounds": 4, "penalty": 3},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "History & Inventions, 5 rounds"))
        self.rounds = min(len(QA_HISTORY), int(self.variant.get("rounds", 5)))
        self.penalty = int(self.variant.get("penalty", 3))

        self.doc = CORPUS_HISTORY.strip()
        self.qa = list(QA_HISTORY[:self.rounds])

        self.scores = [0, 0]
        self.round = 1
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def rules(self) -> str:
        return f"""DOCUMENT QA (Truth Family) - {self.label}. 2 players, simultaneous answers.

GOAL
Score points by answering questions truthfully using ONLY the provided reference document.

SCORING AND THE HALLUCINATION PENALTY (Rule 8.5)
- Correct answer supported by the document: +2 points.
- Abstain when the fact is missing or unknown ("unknown" or "pass"):
    * If fact is absent from document: +1 point (correct abstention).
    * If fact is present in document: 0 points (safe pass).
- INCORRECT OR INVENTED ANSWER: -{self.penalty} points (penalty for hallucination/fabrication!).
Saying "unknown" is ALWAYS safer than guessing or hallucinating facts not in the document.

ACTION FORMAT
    answer <your answer>   OR   unknown   OR   pass
Examples: "answer 1712", "James Watt", "unknown", "pass".
A bare answer string is also accepted. Case does not matter.

REFERENCE DOCUMENT
----------------------------------------
{self.doc}
----------------------------------------
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        return ["unknown", "pass"]  # open-ended answer space

    def normalize(self, seat: int, action: str) -> str | None:
        c = self.clean(action)
        if not c:
            return None
        if c in ("unknown", "pass"):
            return c
        m = _ANS_RE.match(c)
        if m:
            val = m.group(1).strip()
            if val in ("unknown", "pass"):
                return val
            return f"answer {val}"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        curr_q = self.qa[self.round - 1]
        round_res = []

        for seat in (0, 1):
            act = self.normalize(seat, actions[seat])
            val = act.replace("answer ", "").strip() if act else "unknown"
            if val in ("unknown", "pass"):
                if not curr_q["known"]:
                    pts = 1  # Correct abstention
                    verdict = "correct abstention (+1)"
                else:
                    pts = 0  # Missed point, but no penalty
                    verdict = "safe abstention (0)"
            else:
                # Check if answer matches canonical
                is_correct = any(ans in val for ans in curr_q["ans"])
                if is_correct:
                    pts = 2
                    verdict = "correct (+2)"
                else:
                    pts = -self.penalty
                    verdict = f"hallucination/wrong (-{self.penalty})"
            self.scores[seat] += pts
            round_res.append({"seat": seat, "action": act, "pts": pts, "verdict": verdict})

        record = {
            "round": self.round,
            "question": curr_q["q"],
            "known": curr_q["known"],
            "results": round_res,
            "scores": list(self.scores),
        }
        self.history.append(record)
        self.last = record

        if self.round >= self.rounds:
            self.over = True
            if self.scores[0] > self.scores[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won with higher truth score ({self.scores[0]} vs {self.scores[1]})"
            elif self.scores[1] > self.scores[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won with higher truth score ({self.scores[1]} vs {self.scores[0]})"
            else:
                self.winner = None
                self.end_reason = f"draw with equal truth scores ({self.scores[0]}-{self.scores[1]})"
        else:
            self.round += 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        curr_q = self.qa[self.round - 1]
        lines = [
            f"DOCUMENT QA ({self.label}). You are Player {seat}.",
            f"Round {self.round} of {self.rounds}. Current score: you {self.scores[seat]}, opponent {self.scores[opp]}.",
            "",
            "REFERENCE DOCUMENT:",
            self.doc,
            "",
            f"QUESTION FOR ROUND {self.round}:",
            f"  {curr_q['q']}",
            "",
            "Instructions: Answer based strictly on the text above. If the fact is not in the text, reply 'unknown'.",
        ]
        if self.history:
            lines.append("\nPrevious round history:")
            for h in self.history:
                my_r = h["results"][seat]
                opp_r = h["results"][opp]
                lines.append(f"  Round {h['round']} Q: '{h['question'][:40]}...' -> you: {my_r['verdict']}, opp: {opp_r['verdict']}")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.scores),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "round": self.round,
            "rounds": self.rounds,
            "scores": list(self.scores),
            "history": list(self.history),
            "last": self.last,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }

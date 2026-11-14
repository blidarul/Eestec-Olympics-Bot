"""Build protocol messages (prep/start/turn) from arena-lite practice games."""
import os, sys, importlib
ARENA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "arena-lite"))
sys.path.insert(0, ARENA)
from arena.practice import tic_tac_toe, pig, guess_number
GAMES = {"tic_tac_toe": tic_tac_toe, "pig": pig, "guess_number": guess_number}

def game_cls(gid):
    m = GAMES[gid]
    from arena.core import Game
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, Game) and v is not Game)

def build(gid, vi=0, seat=0, seed=1, llm=None):
    C = game_cls(gid); v = C.variants()[vi]; g = C(v, seed)
    turn = lambda n=1: {"type": "turn", "game_index": 1, "turn": n, "observation": g.observation(seat),
                        "legal_actions": g.legal_actions(seat), "seconds": 20, "chat": []}
    llm = llm or {"base_url": "http://x/v1", "api_key": "k-prep", "model": "haiku"}
    prep = {"type": "prep", "game_id": gid, "game_name": gid,
            "variants": [{"label": x.get("label", str(i)), "rules": C(x, seed).rules(),
                          "sample_turn": {"type": "turn", "game_index": 1, "turn": 1, "observation": C(x, seed).observation(0),
                                          "legal_actions": C(x, seed).legal_actions(0), "seconds": 20, "chat": []}}
                         for i, x in enumerate(C.variants())],
            "seconds": 600, "you": "us", "study_seconds": 30, "move_seconds": 20, "llm": llm}
    start = {"type": "start", "match_id": "audit-1", "game_index": 1, "best_of": 1, "game_id": gid, "game_name": gid,
             "variant": v, "rules": g.rules(), "seat": seat, "you": "us", "opponent": "them",
             "match_score": {"you": 0, "opponent": 0}, "study_seconds": 30, "move_seconds": 20, "chat": [], "llm": llm}
    return prep, start, turn, g

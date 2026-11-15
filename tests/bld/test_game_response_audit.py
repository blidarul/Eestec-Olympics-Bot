"""Test game response quality audit for all practice arena games."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("arena-lite"))
from arena import registry


def audit_game(gid, cls):
    score = 0.0
    feedback = []

    # 1. Rules Check (max 2.0 pts)
    variants = cls.variants()
    if not variants:
        feedback.append("No variants found")
        rules_score = 0.0
    else:
        var = variants[0]
        try:
            g = cls(var, seed=42)
            r = g.rules()
            r_score = 0.0
            if len(r) >= 150:
                r_score += 0.5
            if any(k in r.upper() for k in ["GOAL", "OBJECT"]):
                r_score += 0.5
            if any(k in r.upper() for k in ["ACTION", "FORMAT"]):
                r_score += 0.5
            if any(k in r.upper() for k in ["SCORE", "END", "WIN"]):
                r_score += 0.5
            rules_score = r_score
        except Exception as e:
            feedback.append(f"Rules error: {e}")
            rules_score = 0.0
    score += rules_score

    # 2. Observation Check (max 2.0 pts)
    obs_score = 0.0
    try:
        movers = g.to_move()
        if movers:
            seat = movers[0]
            obs = g.observation(seat)
            if len(obs) >= 40:
                obs_score += 0.5
            if f"Player {seat}" in obs or f"seat {seat}" in obs or f"Player {seat}" in obs.title() or "Player" in obs:
                obs_score += 0.5
            if any(k in obs.lower() for k in ["score", "turn", "round", "hand", "ply", "move", "piles", "pots", "board", "chips"]):
                obs_score += 0.5
            if "\n" in obs:
                obs_score += 0.5
    except Exception as e:
        feedback.append(f"Observation error: {e}")
    score += obs_score

    # 3. Action Grammar & Normalization (max 2.0 pts)
    norm_score = 0.0
    try:
        legals = g.legal_actions(seat)
        test_act = None
        if legals:
            test_act = legals[0]
            norm_score += 0.5
        else:
            if gid == "battleship":
                test_act = "fire a1"
            elif gid == "bulls_and_cows":
                test_act = "guess " + "".join(g.alphabet[:g.length])
            elif gid == "colonel_blotto":
                test_act = g.random_action(seat, g.rng)
            elif gid == "guess_number":
                test_act = f"guess {g.lo}"
            elif gid == "wordle_duel":
                test_act = "CRANE" if g.length == 5 else "PLANET"
            elif gid == "elemental_duel":
                test_act = "cast fireball"
            elif gid == "sealed_auction":
                test_act = "bid 50.0"
            elif gid == "taboo_duel":
                test_act = "say the weather is very pleasant today"
            elif gid == "document_qa":
                test_act = "unknown"
            elif gid == "secret_keeper":
                test_act = "say what is the protocol?"
            else:
                test_act = "pass"
            norm_score += 0.5

        if test_act:
            n1 = g.normalize(seat, test_act)
            if n1 is not None:
                norm_score += 0.5
            n2 = g.normalize(seat, "  " + test_act.upper() + "  ")
            if n2 is not None:
                norm_score += 0.5
            else:
                feedback.append("Normalize is case/whitespace sensitive")
            nbogus = g.normalize(seat, "completely_invalid_garbage_12345")
            if nbogus is None:
                norm_score += 0.5
            else:
                feedback.append("Failed to reject invalid action")
                norm_score = max(0.0, norm_score - 0.5)
    except Exception as e:
        feedback.append(f"Normalization error: {e}")
    score += min(2.0, norm_score)

    # 4. State stepping & Lifecycle (max 2.0 pts)
    step_score = 0.0
    try:
        step_count = 0
        while not g.is_over() and step_count < 10:
            cur_movers = g.to_move()
            if not cur_movers:
                break
            acts = {}
            for s in cur_movers:
                l_acts = g.legal_actions(s)
                if l_acts:
                    a = l_acts[0]
                else:
                    if gid == "battleship":
                        a = f"fire {chr(ord('a') + (step_count // g.size))}{(step_count % g.size) + 1}"
                    elif gid == "bulls_and_cows":
                        a = "guess " + "".join(g.alphabet[:g.length])
                    elif gid == "colonel_blotto":
                        a = g.random_action(s, g.rng)
                    elif gid == "guess_number":
                        a = f"guess {g.lo + step_count}"
                    elif gid == "wordle_duel":
                        a = "CRANE" if g.length == 5 else "PLANET"
                    elif gid == "elemental_duel":
                        a = "cast fireball"
                    elif gid == "sealed_auction":
                        a = "bid 50.0"
                    elif gid == "taboo_duel":
                        a = "say the weather is very pleasant today"
                    elif gid == "document_qa":
                        a = "unknown"
                    elif gid == "secret_keeper":
                        a = "say what is the protocol?" if s == 1 else "say protocol classified"
                    else:
                        a = "pass"
                acts[s] = g.normalize(s, a)
            g.apply(acts)
            step_count += 1
        step_score += 1.0

        res = g.result()
        if isinstance(res, dict) and "winner" in res and "scores" in res:
            if isinstance(res["scores"], (list, tuple)) and len(res["scores"]) == 2:
                step_score += 0.5
            if "reason" in res and len(res.get("reason", "")) > 0:
                step_score += 0.5
    except Exception as e:
        feedback.append(f"Lifecycle error: {e}")
    score += step_score

    # 5. Spectator Frame Quality (max 2.0 pts)
    frame_score = 0.0
    try:
        fr = g.frame()
        if isinstance(fr, dict):
            frame_score += 0.5
            json.dumps(fr)
            frame_score += 1.0
            if "to_move" in fr and "over" in fr:
                frame_score += 0.5
    except Exception as e:
        feedback.append(f"Frame error: {e}")
    score += frame_score

    final_score = min(10.0, round(score, 1))
    return final_score, feedback


class TestGameResponseAudit(unittest.TestCase):
    def test_all_games_score_above_threshold(self):
        games = registry.all_games()
        self.assertGreaterEqual(len(games), 25, "Expected at least 25 practice games")
        for gid, cls in sorted(games.items()):
            score, feedback = audit_game(gid, cls)
            self.assertGreaterEqual(score, 9.0, f"Game {gid} scored {score}/10 (< 9.0). Feedback: {feedback}")


if __name__ == "__main__":
    unittest.main()

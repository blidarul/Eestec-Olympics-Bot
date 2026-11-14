"""Test all 15 arena games can be instantiated and stepped through with random actions."""
import os
import sys

# Add arena-lite to sys.path
arena_lite_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "arena-lite"))
if arena_lite_dir not in sys.path:
    sys.path.insert(0, arena_lite_dir)

from arena import registry


def test_all_games_loadable():
    games = registry.all_games()
    expected = [
        "battleship",
        "bulls_and_cows",
        "colonel_blotto",
        "connect_four",
        "dots_and_boxes",
        "guess_number",
        "hex",
        "mini_chess",
        "mini_poker",
        "nim",
        "pig",
        "prisoners_dilemma",
        "rps",
        "tic_tac_toe",
        "wordle_duel",
    ]
    for gid in expected:
        assert gid in games, f"Missing game: {gid}"


def test_game_steps():
    games = registry.all_games()
    for gid, cls in games.items():
        variants = cls.variants()
        assert len(variants) >= 1, f"{gid} has no variants"
        # Test first variant
        var = variants[0]
        game = cls(var, seed=42)
        rules = game.rules()
        assert isinstance(rules, str) and len(rules) > 50, f"{gid} rules string too short"

        # Check turn loop for a few steps
        step = 0
        while not game.is_over() and step < 10:
            movers = game.to_move()
            assert isinstance(movers, list), f"{gid} to_move returned non-list"
            if not movers:
                break
            actions = {}
            for seat in movers:
                obs = game.observation(seat)
                assert isinstance(obs, str) and len(obs) > 0
                legals = game.legal_actions(seat)
                if legals:
                    act = legals[0]
                else:
                    # Provide default legal for games without legal_actions list
                    if gid == "battleship":
                        r = (step % game.size) + 1
                        c = chr(ord('a') + (step // game.size))
                        act = f"fire {c}{r}"
                    elif gid == "bulls_and_cows":
                        act = "guess " + "".join(game.alphabet[:game.length])
                    elif gid == "colonel_blotto":
                        act = game.random_action(seat, game.rng)
                    elif gid == "guess_number":
                        act = f"guess {game.lo + step}"
                    elif gid == "wordle_duel":
                        act = "CRANE" if game.length == 5 else ("PLANET" if game.length == 6 else "TEST")
                    elif gid == "elemental_duel":
                        act = "cast fireball"
                    else:
                        act = "pass"
                norm = game.normalize(seat, act)
                assert norm is not None, f"{gid} failed to normalize {act!r} for seat {seat}"
                actions[seat] = norm
            game.apply(actions)
            step += 1

        frame = game.frame()
        assert isinstance(frame, dict), f"{gid} frame is not dict"
        res = game.result()
        assert isinstance(res, dict) and "winner" in res and "scores" in res


if __name__ == "__main__":
    test_all_games_loadable()
    test_game_steps()
    print("ALL 15+ GAMES PASSED VERIFICATION!")

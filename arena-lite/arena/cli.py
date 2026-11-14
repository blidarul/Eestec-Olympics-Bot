"""Command line: `python -m arena <command>` (run from A:\\eestec\\platform or set PYTHONPATH).

Commands (the dashboard depends on these):
  games
  tournament create --id t1 --name "Tournament 1" --pool-size 4 --weight 1 --tag t1 [--seed N] [--teams path] [--no-pull]
  tournament create --id t3 --name "Tournament 3" --weight 3 --tag t3 --final   (pool = all games, reserved included)
  tournament prep t1 [--parallel 16] [--seconds 600] [--teams a,b] [--games g1,g2] [--order game|team|match] [--retry-failed] [--force] [--keep] [--cap N]
                                    (warm session: prep every team x needed game, then hold the warm containers)
  tournament draw t1 [round]         (six game slots for every playable match of the round)
  tournament start-match t1 <match_id>   (one pending match from the live warm session, max 2 at once)
  tournament run t1 [--rounds all|next] [--parallel 4] [--study 120] [--warm-study 30] [--move 20] [--hold]
                                    (forwarded to the live warm session of t1 when there is one)
  tournament release t1             (end the warm session: shutdown message to every warm container)
  tournament status t1
  roundrobin create --id rr1 --tag t2 [--boards 2] [--seed N] [--pool nonreserved|all|g1,g2] [--teams path] [--no-pull]
  roundrobin prep rr1 / run rr1 / release rr1   (a live session serving the same image tag, e.g. T2's, is reused)
  roundrobin status rr1
  standings
  chatcheck t1 [--teams a,b] [--game tic_tac_toe] [--games 2] [--parallel 3] [--budget 0.75] [--out DIR]
                                    (the organizer probe plays every entrant of t1 and talks to it: does it
                                     talk, does what it hears reach its model calls -> results/t1/chatcheck.json)
  chatcheck --tag t1 [--no-pull] [--image TEAM=REF ...] [--out DIR]   (teams.json images at a tag instead)
  match --a TEAM --b TEAM [--games g1,g2] [--best-of 3] [--tag t1] [--study S] [--move S] [--id ID]
  practice --bot-a "<cmd or image>" --bot-b "<cmd or image>" [--game ID] [--games-dir practice|games]
           [--study S] [--move S] [--env-file path] [--prep [--prep-seconds S]]
  prep --bot "<cmd or image>" --game ID [--seconds S] [--env-file path]   (one local prep run, then shutdown)
  practice-run --team T --tag TAG --game ID --opponent prompt-only|dvloper-house|dvloper-master|mirror|human
               --id RUN [--variant N] [--games 2] [--prep] [--opponent-tag TAG] [--teams path] [--no-pull] [--out DIR]
                                    (the dashboard's Practice page: one team's image on a practice or released
                                     game; results/practice/<team>/runs/<run>.json, nothing counts)
  practice-clean [--run RUN]        (kill the practice containers still running: one run's, or all)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from . import config, randomizer

LITE = True  # build_lite.py flips this: the participant copy only has `practice` and `prep`


def resolve_path(p: str | None) -> Path | None:
    """Absolute as given; relative: current directory first, then the repo root."""
    if not p:
        return None
    path = Path(p)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    return (config.ROOT / path).resolve()


def _csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _out(text: str) -> None:
    print(text, flush=True)


# ------------------------------------------------------------------ games
def cmd_games(args) -> int:
    from . import event, registry
    held = set(event.reserved_games())
    out = []
    for kind, games in (("tournament", registry.tournament_games()), ("practice", registry.practice_games())):
        for cls in games.values():
            out.append({**cls.info(), "kind": kind, "reserved": kind == "tournament" and cls.id in held})
    _out(json.dumps(out, ensure_ascii=True))
    return 0


# ------------------------------------------------------------- tournament
def cmd_t_create(args) -> int:
    from . import tournament
    doc = tournament.create(args.id, args.name or args.id, args.pool_size, args.weight, args.tag, seed=args.seed,
                            teams_path=resolve_path(args.teams), pull=not args.no_pull, pool=_csv(args.pool) or None,
                            seeding=args.seeding, force=args.force, final=args.final, field=args.field,
                            finalists=_csv(args.finalists) or None,
                            house=args.with_house, echo=_out)
    if doc.get("final"):
        reserved = f", final (reserved games in the pool: {', '.join(doc['reserved_in_pool']) or 'none'})"
    else:
        reserved = f", reserved for the final: {', '.join(doc['reserved'])}" if doc.get("reserved") else ""
    _out(f"created {doc['id']}: {len(doc['entrants'])} entrants, pool {', '.join(doc['pool'])}, "
         f"seed {doc['seed']}, seeding {doc['seeding']}, {len(doc['excluded'])} left out{reserved}")
    if doc.get("not_qualified"):
        _out(f"not in the final (round-of-16 placement): {', '.join(t['team'] for t in doc['not_qualified'])}")
    if getattr(args, "prep", False):
        pargs = _prep_parser(argparse.ArgumentParser(add_help=False)).parse_args([])
        pargs.cid, pargs.kind = doc["id"], "tournament"
        return cmd_prep_session(pargs)
    return 0


# ------------------------------------------------------------- warm sessions
def _session_for(cid: str, kind: str):
    """The live warm session that serves `cid` (a round robin also takes one serving its image tag)."""
    from . import prep, session
    _, doc, _ = prep.competition(cid, config.RESULTS)
    tag = doc.get("tag") if kind == "roundrobin" else None
    return session.find(config.RESULTS, cid=cid, tag=tag)


def _forward(sess: dict, cmd: dict) -> int:
    from . import session
    session.forward(sess, cmd, config.RESULTS)
    what = f"{cmd['op']} {cmd.get('id') or ''}".strip()
    _out(f"{what}: queued in the warm session {sess['id']} (pid {sess.get('pid')}, {sess.get('state')}, "
         f"{(sess.get('warm') or {}).get('alive', 0)} warm containers); follow results/{config.safe_name(sess['id'])}/session.json")
    return 0


def _serve(home: str, commands: list[dict], args) -> int:
    from . import session
    sess = session.Session(home, results_dir=config.RESULTS, keep=getattr(args, "keep", False),
                           cap=getattr(args, "cap", None) or config.WARM_CAP,
                           grace=getattr(args, "grace", None) or config.SHUTDOWN_GRACE,
                           teams_path=resolve_path(getattr(args, "teams_file", None)), echo=_out)
    _out(f"warm session {home} (pid {os.getpid()}): holding the warm containers until everything it serves is done"
         + (" (--keep: until `release`)" if sess.keep else "") + f"; stop it with `release {home}`")
    return sess.serve(commands)


def cmd_prep_session(args) -> int:
    """`tournament prep <tid>` / `roundrobin prep <rrid>`."""
    cid, kind = args.cid, args.kind
    from . import prep
    k, doc, _ = prep.competition(cid, config.RESULTS)
    if k != kind:
        raise RuntimeError(f"{cid} is a {k}, not a {kind}")
    cmd = {"op": "prep", "id": cid, "parallel": args.parallel, "seconds": args.seconds, "budget": args.budget,
           "teams": _csv(args.teams), "games": _csv(args.games), "order": args.order, "force": args.force,
           "retry_failed": args.retry_failed, "warm_study": args.warm_study, "move": args.move}
    sess = _session_for(cid, kind)
    if sess:
        return _forward(sess, cmd)
    return _serve(cid, [cmd], args)


def cmd_release(args) -> int:
    cid, kind = args.cid, args.kind
    sess = _session_for(cid, kind)
    if sess:
        return _forward(sess, {"op": "release", "id": cid})
    from .protocol import docker_available, kill_labeled
    n = kill_labeled("eestec-arena.session", cid) if docker_available() else 0
    _out(f"{cid}: no live warm session" + (f"; killed {n} leftover warm container(s)" if n else ""))
    return 0


def _run_command(args, cid: str) -> dict:
    cmd = {"op": "run", "id": cid, "parallel": args.parallel, "study": args.study, "warm_study": args.warm_study,
           "move": args.move, "budget": args.budget, "grace": args.grace, "force": args.force}
    if hasattr(args, "rounds"):
        cmd.update(rounds=args.rounds, best_of=args.best_of)
    return cmd


def cmd_t_run(args) -> int:
    from . import tournament
    sess = _session_for(args.tid, "tournament")
    if sess:
        return _forward(sess, _run_command(args, args.tid))
    if args.hold:
        return _serve(args.tid, [_run_command(args, args.tid)], args)
    doc = tournament.run(args.tid, rounds=args.rounds, parallel=args.parallel, study=args.study, move=args.move,
                         best_of=args.best_of, force=args.force, budget=args.budget, shutdown_grace=args.grace,
                         warm_study=args.warm_study, cap=args.cap or config.WARM_CAP)
    _out(f"{doc['id']}: {doc['status']}")
    return 0


def cmd_t_draw(args) -> int:
    from . import tournament
    doc = tournament.draw_stage(args.tid, args.round, force=args.force, echo=_out)
    _out(f"{doc['id']}: stage draw is ready")
    return 0


def cmd_t_draw_match(args) -> int:
    from . import tournament
    tournament.draw_match(args.tid, args.match_id, force=args.force, echo=_out)
    _out(f"{args.tid}: draw ready for {args.match_id}")
    return 0


def cmd_t_start_match(args) -> int:
    from . import tournament
    sess = _session_for(args.tid, "tournament")
    if sess:
        return _forward(sess, {"op": "start-match", "id": args.tid, "match_id": args.match_id,
                               "best_of": args.best_of, "study": args.study, "warm_study": args.warm_study,
                               "move": args.move, "budget": args.budget, "grace": args.grace,
                               "allow_cold": args.allow_cold, "draw": args.draw})
    raise SystemExit(f"error: {args.tid} has no live warm session; start prep first "
                     f"(`arena tournament prep {args.tid}`)")


def _prep_status_lines(cid: str) -> str:
    from . import prep, session
    out = []
    if prep.prep_path(cid, config.RESULTS).exists():
        out.append(prep.status_text(cid, config.RESULTS))
    for s in session.sessions(config.RESULTS):
        if s.get("id") == cid or cid in (s.get("serving") or []):
            w = s.get("warm") or {}
            mem = f", {w['mem_mb_total']:.0f} MiB (avg {w['mem_mb_avg']:.0f})" if w.get("mem_mb_total") else ""
            out.append(f"warm session {s['id']}: {'alive' if s['alive'] else 'not running'} ({s.get('state')}), "
                       f"{w.get('alive', 0)} warm container(s) of cap {w.get('cap')}{mem}")
    return "\n".join(out)


def cmd_t_status(args) -> int:
    from . import tournament
    _out(tournament.status_text(args.tid))
    extra = _prep_status_lines(args.tid)
    if extra:
        _out(extra)
    return 0


def cmd_standings(args) -> int:
    from . import tournament
    doc = tournament.recompute_standings(config.RESULTS, resolve_path(args.teams))
    for i, t in enumerate(doc["teams"], start=1):
        _out(f"{i:2}. {t['name']:<28} {t['points']:>5}  {t['by_tournament']}")
    info = doc.get("scoring") or {}
    rows = {t["team"]: t for t in doc["teams"]}
    judged = info.get("judging")
    _out("")
    _out(f"composite: tournaments {', '.join(info.get('tournaments_counted') or []) or '-'} "
         f"(max {info.get('max_tournament_points')} pts), round robins "
         f"{', '.join(info.get('round_robins_counted') or []) or '-'}, lowest avg cost/match "
         f"{info.get('lowest_avg_cost')} ({info.get('lowest_avg_cost_team')})")
    head = f"     {'team':<28} {'T/30':>6} {'RR/10':>6} {'C&R/5':>6} {'auto/45':>8}"
    _out(head + (f" {'judges':>7} {'total':>6}" if judged else ""))
    for team in info.get("order") or []:
        t = rows.get(team)
        c = (t or {}).get("composite")
        if not c:
            continue
        line = (f"{c['rank']:3}. {t['name']:<28} {c['tournaments']:>6} {c['round_robin']:>6} "
                f"{c['cost_robustness']:>6} {c['automated_total']:>8}")
        if judged:
            j = c.get("judges")
            jt = round((j.get("presentation") or 0) + (j.get("harness_design") or 0), 2) if j else "-"
            line += f" {jt:>7} {c['total'] if c.get('total') is not None else '-':>6}"
        _out(line)
    for w in info.get("warnings") or []:
        _out(f"warning: {w}")
    return 0


# ------------------------------------------------------------- round robin
def cmd_rr_create(args) -> int:
    from . import roundrobin
    doc = roundrobin.create(args.id, args.tag, boards=args.boards, seed=args.seed, pool=args.pool or "tournament",
                            name=args.name, teams_path=resolve_path(args.teams), pull=not args.no_pull,
                            force=args.force, house=args.with_house, echo=_out)
    _out(f"created {doc['id']}: {len(doc['entrants'])} entrants, {len(doc['pairings'])} pairings in "
         f"{doc['rounds_total']} rounds, {doc['boards']} board(s) each, pool ({doc['pool_mode']}) "
         f"{', '.join(doc['pool'])}, seed {doc['seed']}, {len(doc['excluded'])} left out")
    return 0


def cmd_rr_run(args) -> int:
    from . import roundrobin
    sess = _session_for(args.rrid, "roundrobin")
    if sess:
        return _forward(sess, _run_command(args, args.rrid))
    if args.hold:
        return _serve(args.rrid, [_run_command(args, args.rrid)], args)
    doc = roundrobin.run(args.rrid, parallel=args.parallel, study=args.study, move=args.move, force=args.force,
                         budget=args.budget, shutdown_grace=args.grace, teams_path=resolve_path(args.teams),
                         warm_study=args.warm_study, cap=args.cap or config.WARM_CAP)
    _out(f"{doc['id']}: {doc['status']}")
    return 0


def cmd_rr_status(args) -> int:
    from . import roundrobin
    _out(roundrobin.status_text(args.rrid))
    extra = _prep_status_lines(args.rrid)
    if extra:
        _out(extra)
    return 0


# ------------------------------------------------------------- chat check
def cmd_chatcheck(args) -> int:
    """`chatcheck <tid>` / `chatcheck --tag t1`: the organizer probe plays each image and talks to it."""
    from . import chatcheck
    if not args.cid and not args.tag:
        raise SystemExit("error: give a tournament / round robin id, or --tag")
    overrides = {}
    for spec in args.image or []:
        team, sep, ref = spec.partition("=")
        if not sep or not team.strip() or not ref.strip():
            raise SystemExit(f"error: --image wants TEAM=REF, got {spec!r}")
        overrides[team.strip()] = ref.strip()
    only = set(_csv(args.teams))
    excluded: list[dict] = []
    if args.cid and not args.tag:
        if overrides:
            raise SystemExit("error: --image needs --tag (a competition checks the images pinned at its creation)")
        kind, doc, targets = chatcheck.targets_from_competition(args.cid)
        cid, tag = args.cid, doc.get("tag")
        out_dir = resolve_path(args.out) or config.RESULTS / config.safe_name(cid)
    else:
        targets, excluded = chatcheck.targets_from_tag(args.tag, teams_path=resolve_path(args.teams_file),
                                                       pull=not args.no_pull, overrides=overrides, echo=_out)
        kind, tag = "tag", args.tag
        cid = args.cid or f"chatcheck-{config.safe_name(args.tag, 20)}"
        out_dir = resolve_path(args.out) or config.RESULTS / config.safe_name(cid)
    if only:
        unknown = only - {t.team for t in targets}
        if unknown:
            raise SystemExit(f"error: not an entrant: {', '.join(sorted(unknown))}")
        targets = [t for t in targets if t.team in only]
    if not targets:
        raise SystemExit("error: nothing to check")
    _out(f"chat check {cid}: {len(targets)} image(s), {args.game} x{args.games}, {args.parallel} at a time "
         f"-> {out_dir / chatcheck.FILE}")
    doc = chatcheck.run_check(cid, targets, out_dir=out_dir, kind=kind, tag=tag, game=args.game, games=args.games,
                              study=args.study, move=args.move, budget=args.budget, parallel=args.parallel,
                              log_wait=args.log_wait, grace=args.grace, merge=bool(only), seed=args.seed,
                              excluded=excluded, variant=None if args.variant < 0 else args.variant, echo=_out)
    _out("")
    _out(chatcheck.table(doc))
    _out(f"wrote {out_dir / chatcheck.FILE}")
    return 0


# ------------------------------------------------------------- release games to the practice kit
def cmd_release_games(args) -> int:
    """`release <tournament id>`: its games become practice games in participant-kit/arena-lite."""
    from . import build_lite, event
    from . import registry as reg
    path = config.RELEASED_JSON
    doc = config.read_json(path, {}) or {}
    games = [g for g in doc.get("games") or [] if isinstance(g, str)]
    if args.list:
        _out("released: " + (", ".join(games) or "(none)"))
        return 0
    wanted = _csv(args.games)
    source = "list"
    if args.tid:
        tdoc = config.read_json(config.RESULTS / config.safe_name(args.tid) / "tournament.json")
        if not tdoc:
            raise SystemExit(f"error: no tournament {args.tid}")
        if tdoc.get("status") != "done" and not args.force:
            raise SystemExit(f"error: {args.tid} is {tdoc.get('status')!r}, not done: release its games after it "
                             f"is played (or --force)")
        if tdoc.get("final") and not args.force:
            raise SystemExit("error: the final's games are not released (use --games, or --force)")
        wanted, source = list(tdoc.get("pool") or []), args.tid
    if not wanted:
        raise SystemExit("error: give a tournament id, --games g1,g2 or --list")
    known = reg.tournament_games()
    unknown = [g for g in wanted if g not in known]
    if unknown:
        raise SystemExit(f"error: not tournament games: {', '.join(unknown)}")
    held = [g for g in wanted if g in event.reserved_games()]
    if held and not args.force:
        raise SystemExit(f"error: reserved for the final, not released: {', '.join(held)} (--force overrides)")
    if args.undo:
        games = [g for g in games if g not in wanted]
    else:
        games = list(dict.fromkeys(games + wanted))
    doc["games"] = games
    doc.setdefault("log", []).append({"at": config.now_iso(), "source": source, "undo": bool(args.undo),
                                      "games": wanted})
    config.write_json_atomic(path, doc)
    out = build_lite.build()
    listing = build_lite._smoke_test(out)
    _out(f"{'withdrew' if args.undo else 'released'}: {', '.join(wanted)}")
    _out(f"practice games now in {out}: {', '.join(l.split()[0] for l in listing.splitlines() if l.strip())}")
    _out("hand the updated participant-kit/arena-lite folder to the teams")
    return 0


# ------------------------------------------------------------- egress
def cmd_egress(args) -> int:
    """Per-team summary of the egress proxy log (internet traffic of the bot containers)."""
    from . import egress
    from .tournament import load_teams
    ids = [t["id"] for t in load_teams(resolve_path(args.teams))["teams"]]
    log = resolve_path(args.log) or config.EGRESS_LOG
    summary = egress.summarize(egress.read_log(log), ids)
    if args.json:
        _out(json.dumps(summary, indent=2))
    else:
        _out(f"egress log {log}")
        _out(egress.table(summary, team=args.team, blocked=args.blocked))
    return 0


# ------------------------------------------------------------- exhibition
def cmd_match(args) -> int:
    from . import registry, tournament
    from .gateway import keys_from_env
    from .match import Entrant, ListPicker, MatchRunner, PoolPicker
    teams = {t["id"]: t for t in tournament.load_teams(resolve_path(args.teams))["teams"]}
    entrants = []
    for side, tid in (("a", args.a), ("b", args.b)):
        if tid not in teams:
            raise SystemExit(f"error: unknown team {tid!r} (see platform/teams.json)")
        fields, msg = tournament.resolve_team_image(teams[tid], args.tag, pull=not args.no_pull)
        if fields is None:
            raise SystemExit(f"error: {msg}")
        if fields.get("cmd"):
            entrants.append(Entrant(team=tid, name=teams[tid].get("name", tid), cmd=fields["cmd"], seed=1 if side == "a" else 2))
        else:
            entrants.append(Entrant(team=tid, name=teams[tid].get("name", tid), image=fields["ref"], seed=1 if side == "a" else 2))
    mid = args.id or f"x-{config.safe_name(args.a, 20)}-vs-{config.safe_name(args.b, 20)}-{time.strftime('%Y%m%d-%H%M%S')}"
    seed = args.seed if args.seed is not None else randomizer.new_seed()
    reg = registry.all_games()
    if args.games:
        picker = ListPicker(_csv(args.games), seed, mid, reg)
        pool = _csv(args.games)
    else:  # games reserved for the final stay out of exhibitions (replays are public)
        from . import event
        tgames = sorted(registry.tournament_games())
        held, _ = event.split_reserved(tgames, event.reserved_games())
        pool = [g for g in tgames if g not in held] or tgames or sorted(registry.practice_games())
        picker = PoolPicker(seed, mid, pool, reg)
    if any(e.image for e in entrants):
        from .protocol import ensure_network
        ensure_network(config.NETWORK)
    xdir = config.RESULTS / "exhibition"
    keys = keys_from_env(budget=args.budget, extra_metadata={"tournament": "exhibition"})
    doc = MatchRunner(entrants[0], entrants[1], match_id=mid, picker=picker, out_path=xdir / "matches" / f"{mid}.json",
                      log_dir=xdir / "logs", tournament="exhibition", best_of=args.best_of, study=args.study,
                      move=args.move, keys=keys, model=args.model, shutdown_grace=args.grace, echo=_out,
                      extra={"seed": seed, "pool": pool, "model": args.model}).run()
    _out(f"wrote {xdir / 'matches' / (mid + '.json')}  winner: {doc['winner']}")
    return 0


# --------------------------------------------------------------- practice
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "gateway", "host.docker.internal")


def _practice_entrant(spec: str, team: str, env_file: dict, network_opt: str | None):
    from .match import Entrant
    from .protocol import looks_like_image, network_exists, strip_prefix
    base = env_file.get("LLM_BASE_URL", "")
    # Only LLM_* (the key is passed separately) and the team's own BOT_* settings reach
    # the bot, so a team .env holding registry credentials never leaks into it.
    extra = {k: v for k, v in env_file.items()
             if (k.startswith("LLM_") and k != "LLM_API_KEY") or k.startswith("BOT_")}
    if looks_like_image(spec):
        # A gateway on this machine is reached as `gateway` on the arena network,
        # or via host.docker.internal from Docker's default network.
        image = strip_prefix(spec)
        url = urlparse(base) if base else None
        local = url is None or url.hostname in _LOCAL_HOSTS
        if network_opt is None:
            network = config.NETWORK if local and network_exists(config.NETWORK) else None
        else:
            network = None if network_opt in ("", "default", "bridge") else network_opt
        if local:
            if network == config.NETWORK:
                base = config.CONTAINER_LLM_BASE_URL
            elif network is None:
                port = (url.port if url else None) or 4000
                path = (url.path if url and url.path else "/v1")
                base = f"http://host.docker.internal:{port}{path}"
        extra["LLM_BASE_URL"] = base
        return Entrant(team=team, image=image, network=network, env=extra, llm_base_url=base)
    extra["LLM_BASE_URL"] = base or config.HOST_LLM_BASE_URL
    return Entrant(team=team, cmd=strip_prefix(spec), env=extra, llm_base_url=extra["LLM_BASE_URL"])


def _local_prep(pool, entrants: list, games: list, seconds: float, keys, model: str, warm_study: float,
                move: float, echo) -> list[dict]:
    """Prep every entrant for every game (all at once, like the arena does after the freeze)."""
    from concurrent.futures import ThreadPoolExecutor
    from .warm import prep_one
    seed = randomizer.new_seed()
    jobs = [(e, g) for g in games for e in entrants]

    def one(job):
        e, g = job
        rec = prep_one(pool, e, g, keys=keys, seconds=seconds, seed=seed, model=model, study=warm_study, move=move,
                       prep_id=f"prep-local-{g.id}")
        took = f" after {rec['seconds']:g} s" if rec.get("seconds") is not None else ""
        echo(f"prep {e.team} x {g.id}: {rec['status']}{took}{' (' + rec['note'] + ')' if rec.get('note') else ''}")
        return {"team": e.team, "game": g.id, **rec}
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(jobs)))) as ex:
        return list(ex.map(one, jobs))


def cmd_prep(args) -> int:
    """One local prep run: start the bot, send `prep` for one game, wait for `ready`, then shut it down."""
    from . import registry
    from .match import StaticKeys
    from .warm import WarmPool, prep_message
    reg = registry.all_games()
    if args.game not in reg:
        raise SystemExit(f"error: unknown game {args.game!r}; try `practice --list`")
    env_path = resolve_path(args.env_file)
    if env_path and not env_path.is_file():
        raise SystemExit(f"error: env file not found: {env_path}")
    env_file = config.load_env_file(env_path) if env_path else {}
    key = env_file.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY", "")
    model = env_file.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or config.MODEL
    e = _practice_entrant(args.bot, args.name, env_file, args.network)
    pdir = config.RESULTS / "practice"
    pool = WarmPool("prep-local", pdir / "logs", grace=args.grace)
    if args.show:
        msg = prep_message(reg[args.game], e.team, seconds=args.seconds, llm={"base_url": "...", "api_key": "...",
                                                                             "model": model})
        _out(json.dumps(msg, ensure_ascii=False, indent=1))
        return 0
    _out(f"prep {e.team} = {args.bot!r} for {args.game} ({args.seconds:g} s)")
    try:
        recs = _local_prep(pool, [e], [reg[args.game]], args.seconds, StaticKeys(key), model, args.warm_study,
                           args.move, _out)
    finally:
        pool.release_all(args.grace)
    rec = recs[0]
    _out(f"result: {rec['status']}" + (f" after {rec['seconds']:g} s" if rec.get("seconds") is not None else ""))
    _out(f"bot stderr log: {pdir / 'logs' / 'warm'}")
    _out(f"memory folder: {e.memory_dir or config.MEMORY / config.safe_name(e.team)}")
    return 0 if rec["status"] == "ready" else 1


def cmd_practice(args) -> int:
    from . import registry
    from .match import ListPicker, MatchRunner, PoolPicker, StaticKeys
    reg = registry.all_games()
    pool_games = registry.practice_games() if args.games_dir == "practice" else registry.tournament_games()
    if args.list:
        for cls in pool_games.values():
            _out(f"{cls.id:<20} {cls.name}  [{', '.join(v.get('label', '') for v in cls.variants())}]")
        return 0
    if not args.bot_a or not args.bot_b:
        raise SystemExit("error: --bot-a and --bot-b are required")
    env_path = resolve_path(args.env_file)
    if env_path and not env_path.is_file():
        raise SystemExit(f"error: env file not found: {env_path}")
    env_file = config.load_env_file(env_path) if env_path else {}
    key = env_file.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY", "")
    model = env_file.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or config.MODEL
    a = _practice_entrant(args.bot_a, args.name_a, env_file, args.network)
    b = _practice_entrant(args.bot_b, args.name_b, env_file, args.network)
    if a.team == b.team:
        b.team = b.name = b.team + "-2"
    mid = args.id or f"p-{time.strftime('%Y%m%d-%H%M%S')}"
    seed = args.seed if args.seed is not None else randomizer.new_seed()
    if args.game:
        if args.game not in reg:
            raise SystemExit(f"error: unknown game {args.game!r}; try --list")
        picker = ListPicker([args.game], seed, mid, reg)
    else:
        if not pool_games:
            raise SystemExit(f"error: no games in arena/{args.games_dir}")
        picker = PoolPicker(seed, mid, sorted(pool_games), reg)
    pdir = config.RESULTS / "practice"
    out_path = pdir / "matches" / f"{mid}.json"
    echo = (lambda s: None) if args.quiet else _out
    _out(f"practice {mid}: {a.team} = {args.bot_a!r} vs {b.team} = {args.bot_b!r} (seed {seed})")
    pool = None
    if args.prep:  # the tournament flow: one warm container per bot per game, prepared before the match
        from .warm import WarmPool
        pool = WarmPool(mid, pdir / "logs", grace=args.grace)
        games = [reg[args.game]] if args.game else [reg[g] for g in sorted(pool_games)]
        _out(f"prep: {len(games)} game(s) x 2 bots, {args.prep_seconds:g} s each, all at once")
        _local_prep(pool, [a, b], games, args.prep_seconds, StaticKeys(key), model, args.warm_study, args.move, _out)
    try:
        doc = MatchRunner(a, b, match_id=mid, picker=picker, out_path=out_path, log_dir=pdir / "logs",
                          tournament="practice", best_of=args.best_of, study=args.study, move=args.move,
                          keys=StaticKeys(key), model=model, shutdown_grace=args.grace, echo=echo,
                          extra={"seed": seed}, pool=pool, warm_study=args.warm_study).run()
    finally:
        if pool is not None:
            pool.release_all(args.grace)
    sc = doc["score"]
    _out(f"final: {a.team} {sc[a.team]} - {sc[b.team]} {b.team}; winner {doc['winner']} ({doc['decided_by']})")
    _out(f"match file: {out_path}")
    _out(f"bot stderr logs: {pdir / 'logs'}" + (" (warm containers: logs/warm/)" if pool is not None else ""))
    return 0


# ------------------------------------------------------- practice runs (the dashboard's Practice page)
def cmd_practice_run(args) -> int:
    from . import practice_run
    try:
        doc = practice_run.run_stoppable(args.team, args.tag, args.game, args.opponent, run_id=args.id,
                               variant=None if args.variant is None or args.variant < 0 else args.variant,
                               games=args.games, prep=args.prep, out_dir=resolve_path(args.out),
                               teams_path=resolve_path(args.teams), pull=not args.no_pull,
                               opponent_tag_override=args.opponent_tag, prep_seconds=args.prep_seconds,
                               study=args.study, warm_study=args.warm_study, move=args.move, idle=args.idle,
                               budget=args.budget, grace=args.grace, seed=args.seed, echo=_out)
    except practice_run.PracticeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if doc.get("status") != "done":
        _out(f"practice {args.id}: {doc.get('status')} ({doc.get('error') or ''})")
        return 1
    sc = doc["score"]
    _out(f"practice {args.id}: {doc['a']} {sc[doc['a']]} - {sc[doc['b']]} {doc['b']}")
    return 0


def cmd_practice_clean(args) -> int:
    from . import practice_run
    if args.run and not practice_run.RUN_ID_RE.match(args.run):
        raise SystemExit("error: bad run id")
    n = practice_run.clean(args.run)
    _out(f"practice containers killed: {n}")
    return 0


# ------------------------------------------------------------------ misc
def cmd_immutable(args) -> int:
    from . import harbor
    ok, msg = harbor.make_tags_immutable(args.project, args.pattern)
    _out(f"{args.project}: {msg}")
    return 0 if ok else 1


# ---------------------------------------------------------------- parser
def _clock_args(p, study=config.STUDY_SECONDS, move=config.MOVE_SECONDS):
    p.add_argument("--study", type=float, default=study,
                   help=f"study clock per game of a cold container (no warm one for the drawn game), seconds (default {study})")
    p.add_argument("--warm-study", type=float, default=config.WARM_STUDY_SECONDS,
                   help=f"study clock per game of a warm (prepared) container, seconds (default {config.WARM_STUDY_SECONDS})")
    p.add_argument("--move", type=float, default=move, help=f"move clock, seconds (default {move})")
    p.add_argument("--grace", type=float, default=config.SHUTDOWN_GRACE, help="seconds a bot gets to exit at the end")


def _prep_parser(p):
    """Options of `tournament prep` / `roundrobin prep` (also the defaults of `tournament create --prep`)."""
    p.add_argument("--parallel", type=int, default=config.PREP_PARALLEL,
                   help=f"prep runs at a time (default {config.PREP_PARALLEL}; each container gets {config.DOCKER_CPUS} CPUs)")
    p.add_argument("--seconds", type=float, default=config.PREP_SECONDS,
                   help=f"prep time per container (default {config.PREP_SECONDS})")
    p.add_argument("--teams", help="only these team ids (comma-separated)")
    p.add_argument("--games", help="only these pool games (comma-separated)")
    p.add_argument("--order", choices=("game", "team", "match"), default="match",
                   help="prep order: game by game, team by team, or in match order (default)")
    p.add_argument("--force", action="store_true", help="prepare again pairs that are warm or ended timeout/error")
    p.add_argument("--retry-failed", action="store_true", help="prepare again the pairs that ended timeout/error")
    p.add_argument("--budget", type=float, default=config.PREP_BUDGET, help="LLM budget per prep run (USD)")
    p.add_argument("--keep", action="store_true", help="hold the warm containers until `release` (not just until done)")
    p.add_argument("--cap", type=int, default=config.WARM_CAP, help=f"warm containers alive at once (default {config.WARM_CAP})")
    p.add_argument("--warm-study", type=float, default=config.WARM_STUDY_SECONDS,
                   help="in-match study clock announced to warm containers")
    p.add_argument("--move", type=float, default=config.MOVE_SECONDS, help="move clock announced in `prep`")
    p.add_argument("--grace", type=float, default=config.SHUTDOWN_GRACE, help="seconds a container gets to exit")
    return p


def _local_prep_parser(sub):
    p = sub.add_parser("prep", help="one local prep run: send your bot `prep` for one game and wait for `ready`")
    p.add_argument("--bot", required=True, help='command ("python bot.py") or docker image; prefix with cmd: or image: to force')
    p.add_argument("--game", required=True, help="game id (see `practice --list`)")
    p.add_argument("--name", default="bot-a", help="team name shown to the bot (`you`)")
    p.add_argument("--seconds", type=float, default=config.PREP_SECONDS, help=f"prep time (default {config.PREP_SECONDS})")
    p.add_argument("--env-file", help="file with LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (your dev key)")
    p.add_argument("--network", help="docker network for image bots (default: eestec-arena if it exists)")
    p.add_argument("--show", action="store_true", help="print the prep message and exit (no bot is started)")
    p.add_argument("--warm-study", type=float, default=config.WARM_STUDY_SECONDS,
                   help="in-match study clock announced in `prep`")
    p.add_argument("--move", type=float, default=config.MOVE_SECONDS, help="move clock announced in `prep`")
    p.add_argument("--grace", type=float, default=config.SHUTDOWN_GRACE, help="seconds the bot gets to exit after `shutdown`")
    p.set_defaults(fn=cmd_prep)


def _practice_parser(sub):
    p = sub.add_parser("practice", help="run two bots against each other locally")
    p.add_argument("--bot-a", help='command ("python bot.py") or docker image; prefix with cmd: or image: to force')
    p.add_argument("--bot-b", help="same as --bot-a")
    p.add_argument("--name-a", default="bot-a")
    p.add_argument("--name-b", default="bot-b")
    p.add_argument("--game", help="play only this game id (default: random practice game per game)")
    p.add_argument("--games-dir", choices=("practice", "games"), default="practice")
    p.add_argument("--best-of", type=int, default=config.BEST_OF)
    p.add_argument("--seed", type=int)
    p.add_argument("--id", help="match id (default p-<timestamp>)")
    p.add_argument("--env-file", help="file with LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (your dev key)")
    p.add_argument("--network", help="docker network for image bots (default: eestec-arena if it exists)")
    p.add_argument("--quiet", action="store_true", help="only print the final result")
    p.add_argument("--list", action="store_true", help="list the available games and exit")
    p.add_argument("--prep", action="store_true",
                   help="tournament flow: prep each bot once per game first (warm containers), then play")
    p.add_argument("--prep-seconds", type=float, default=config.PREP_SECONDS,
                   help=f"prep time per container with --prep (default {config.PREP_SECONDS})")
    _clock_args(p)
    p.set_defaults(fn=cmd_practice)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m arena", description="EESTEC AI Harness Arena engine")
    sub = ap.add_subparsers(dest="command", required=True)
    if LITE:
        _practice_parser(sub)
        _local_prep_parser(sub)
        return ap

    sub.add_parser("games", help="JSON list of all games").set_defaults(fn=cmd_games)

    t = sub.add_parser("tournament", help="create / run / inspect tournaments")
    tsub = t.add_subparsers(dest="tcommand", required=True)
    c = tsub.add_parser("create")
    c.add_argument("--id", required=True)
    c.add_argument("--name")
    c.add_argument("--pool-size", type=int, default=None,
                   help="games in the random pool (default 4; with --final: all tournament games)")
    c.add_argument("--weight", type=float, default=1)
    c.add_argument("--tag", required=True)
    c.add_argument("--seed", type=int)
    c.add_argument("--teams", help="teams file (default platform/teams.json)")
    c.add_argument("--no-pull", action="store_true", help="use local images only (no docker pull)")
    c.add_argument("--pool", help="explicit comma-separated game pool instead of a random one")
    c.add_argument("--seeding", choices=("auto", "random", "standings"), default="random",
                   help="bracket order: random = lucky draw (default, every tournament); standings; auto")
    c.add_argument("--field", type=int, default=None,
                   help=f"only the top N play: of the round-robin table, or of the standings when no round robin "
                        f"is finished (default: {config.FINAL_FIELD} with --final, else everyone; 0 = everyone)")
    c.add_argument("--finalists",
                   help="comma-separated team ids that play, set by hand (overrides --field); "
                        "every other team gets the round-of-16 placement")
    c.add_argument("--with-house", action="store_true",
                   help="also enter the organizers' bots (kind house / baseline); by default only student teams play")
    c.add_argument("--force", action="store_true", help="replace an existing started tournament (archived)")
    c.add_argument("--final", action="store_true",
                   help="the final (T3): pool = all tournament games, games reserved for the final included")
    c.add_argument("--prep", action="store_true",
                   help="then start the warm session and prep every team x pool game (defaults of `tournament prep`)")
    c.set_defaults(fn=cmd_t_create)
    r = tsub.add_parser("run")
    r.add_argument("tid")
    r.add_argument("--rounds", choices=("all", "next"), default="all")
    r.add_argument("--parallel", type=int, default=config.PARALLEL)
    r.add_argument("--best-of", type=int, default=config.BEST_OF)
    r.add_argument("--budget", type=float, default=config.MAX_BUDGET, help="LLM budget per bot per match (USD)")
    r.add_argument("--force", action="store_true", help="ignore a stale run lock")
    r.add_argument("--hold", action="store_true",
                   help="become the warm session: keep the containers between rounds (until done or `release`)")
    r.add_argument("--cap", type=int, default=None, help=f"warm containers alive at once (default {config.WARM_CAP})")
    _clock_args(r)
    r.set_defaults(fn=cmd_t_run)
    tp = _prep_parser(tsub.add_parser("prep", help="warm session: prep every team x pool game, then hold"))
    tp.add_argument("cid", metavar="tid")
    tp.set_defaults(fn=cmd_prep_session, kind="tournament")
    tr = tsub.add_parser("release", help="end the warm session of a tournament (shutdown every warm container)")
    tr.add_argument("cid", metavar="tid")
    tr.set_defaults(fn=cmd_release, kind="tournament")
    td = tsub.add_parser("draw", help="draw the fixed game sequence for one round")
    td.add_argument("tid")
    td.add_argument("round", nargs="?", type=int, help="round number (default: the next undrawn round)")
    td.add_argument("--force", action="store_true", help="redraw matches that already have a draw")
    td.set_defaults(fn=cmd_t_draw)
    dm = tsub.add_parser("draw-match", help="draw one match without waiting for its whole round")
    dm.add_argument("tid")
    dm.add_argument("match_id")
    dm.add_argument("--force", action="store_true")
    dm.set_defaults(fn=cmd_t_draw_match)
    sm = tsub.add_parser("start-match", help="start exactly one pending match from the live warm session")
    sm.add_argument("tid")
    sm.add_argument("match_id")
    sm.add_argument("--best-of", type=int, default=config.BEST_OF)
    sm.add_argument("--budget", type=float, default=config.MAX_BUDGET)
    sm.add_argument("--allow-cold", action="store_true",
                    help="start even if some required specialists are missing (they play cold)")
    sm.add_argument("--draw", action="store_true",
                    help="draw this match first when the stage has no draw yet")
    _clock_args(sm)
    sm.set_defaults(fn=cmd_t_start_match)
    s = tsub.add_parser("status")
    s.add_argument("tid")
    s.set_defaults(fn=cmd_t_status)

    rr = sub.add_parser("roundrobin", help="create / run / inspect the duplicate round robin")
    rsub = rr.add_subparsers(dest="rcommand", required=True)
    rc = rsub.add_parser("create")
    rc.add_argument("--id", required=True)
    rc.add_argument("--tag", required=True, help="image tag to pull for every team (e.g. t2)")
    rc.add_argument("--name")
    rc.add_argument("--boards", type=int, default=2, help="boards per pairing; each board is played twice (default 2)")
    rc.add_argument("--seed", type=int)
    rc.add_argument("--pool", default="tournament",
                    help="tournament (default: the games of every non-final tournament so far, i.e. T1's 4 + "
                         "T2's 8), nonreserved, all, or g1,g2,...")
    rc.add_argument("--with-house", action="store_true",
                    help="also enter the organizers' bots; by default only student teams play")
    rc.add_argument("--teams", help="teams file (default platform/teams.json)")
    rc.add_argument("--no-pull", action="store_true", help="use local images only (no docker pull)")
    rc.add_argument("--force", action="store_true", help="replace an existing started round robin (archived)")
    rc.set_defaults(fn=cmd_rr_create)
    rr_run = rsub.add_parser("run")
    rr_run.add_argument("rrid")
    rr_run.add_argument("--parallel", type=int, default=config.PARALLEL)
    rr_run.add_argument("--budget", type=float, default=config.MAX_BUDGET, help="LLM budget per bot per match (USD)")
    rr_run.add_argument("--force", action="store_true", help="ignore a stale run lock")
    rr_run.add_argument("--teams", help="teams file used for the standings names")
    rr_run.add_argument("--hold", action="store_true", help="become the warm session (keep the containers until done)")
    rr_run.add_argument("--cap", type=int, default=None, help=f"warm containers alive at once (default {config.WARM_CAP})")
    _clock_args(rr_run)
    rr_run.set_defaults(fn=cmd_rr_run)
    rp = _prep_parser(rsub.add_parser("prep", help="prep every team x pool game (reuses a live session on the same tag)"))
    rp.add_argument("cid", metavar="rrid")
    rp.set_defaults(fn=cmd_prep_session, kind="roundrobin")
    rrl = rsub.add_parser("release", help="end the warm session serving a round robin")
    rrl.add_argument("cid", metavar="rrid")
    rrl.set_defaults(fn=cmd_release, kind="roundrobin")
    rs = rsub.add_parser("status")
    rs.add_argument("rrid")
    rs.set_defaults(fn=cmd_rr_status)

    m = sub.add_parser("match", help="exhibition match between two registered teams")
    m.add_argument("--a", required=True)
    m.add_argument("--b", required=True)
    m.add_argument("--games", help="comma-separated game ids, played in order (default: random tournament games)")
    m.add_argument("--best-of", type=int, default=config.BEST_OF)
    m.add_argument("--tag", default="latest")
    m.add_argument("--id")
    m.add_argument("--seed", type=int)
    m.add_argument("--teams")
    m.add_argument("--no-pull", action="store_true")
    m.add_argument("--model", default=config.MODEL, help="gateway model alias for both bots (default haiku)")
    m.add_argument("--budget", type=float, default=config.MAX_BUDGET)
    _clock_args(m)
    m.set_defaults(fn=cmd_match)

    _practice_parser(sub)
    _local_prep_parser(sub)

    pr = sub.add_parser("practice-run", help="one practice run for the dashboard's Practice page (nothing counts)")
    pr.add_argument("--team", required=True, help="the team practising (a student team of the teams file)")
    pr.add_argument("--tag", required=True, help="tag of the team's own image")
    pr.add_argument("--game", required=True, help="a practice game or a game released for practice")
    pr.add_argument("--opponent", required=True, choices=("prompt-only", "dvloper-house", "dvloper-master", "mirror",
                                                          "human"))
    pr.add_argument("--id", required=True, help="run id (p<yyyymmdd>-<hhmmss>-<4 hex>)")
    pr.add_argument("--variant", type=int, default=None, help="variant index (default: random)")
    pr.add_argument("--games", type=int, default=2, help="games in the run, 1-3, seats swapped (default 2)")
    pr.add_argument("--prep", action="store_true", help="real prep first (warm containers), then play")
    pr.add_argument("--prep-seconds", type=float, default=config.PREP_SECONDS,
                    help=f"prep time per container, at most {config.PREP_SECONDS}")
    pr.add_argument("--opponent-tag", help="image tag of the organizers' bots (default: the entry's practice_tag, "
                                           "ARENA_PRACTICE_TAG, t1)")
    pr.add_argument("--idle", type=float, default=config.HUMAN_IDLE_SECONDS,
                    help="seconds a person may take for a move before the run is abandoned")
    pr.add_argument("--teams", help="teams file (default platform/teams.json)")
    pr.add_argument("--no-pull", action="store_true", help="use local images only (no docker pull)")
    pr.add_argument("--out", help="output folder (default results/practice/<team>)")
    pr.add_argument("--budget", type=float, default=config.MAX_BUDGET, help="LLM budget per bot for the run (USD)")
    pr.add_argument("--seed", type=int)
    _clock_args(pr)
    pr.set_defaults(fn=cmd_practice_run)
    pc = sub.add_parser("practice-clean", help="kill practice containers that are still running")
    pc.add_argument("--run", help="only this run's containers (default: all practice containers)")
    pc.set_defaults(fn=cmd_practice_clean)

    st = sub.add_parser("standings", help="recompute results/standings.json")
    st.add_argument("--teams")
    st.set_defaults(fn=cmd_standings)

    cc = sub.add_parser("chatcheck", help="chat check: the organizer probe plays each image and talks to it")
    cc.add_argument("cid", nargs="?", metavar="tid", help="tournament or round robin id (its pinned entrant images)")
    cc.add_argument("--tag", help="check the teams.json images at this tag instead of a competition's")
    cc.add_argument("--teams", help="only these team ids (comma-separated); their results replace the old ones")
    cc.add_argument("--image", action="append", metavar="TEAM=REF",
                    help="with --tag: check this image for TEAM instead of <team image>:<tag> (repeatable)")
    cc.add_argument("--no-pull", action="store_true", help="with --tag: use local images only (no docker pull)")
    cc.add_argument("--teams-file", help="teams file for --tag (default platform/teams.json)")
    cc.add_argument("--game", default="tic_tac_toe", help="the check game (its legal actions must be listed)")
    cc.add_argument("--games", type=int, default=2, help="games per check match, all played, seats swapped")
    cc.add_argument("--variant", type=int, default=0, help="variant index of the game (default 0; -1 = random)")
    cc.add_argument("--parallel", type=int, default=3, help="check matches at a time (default 3)")
    cc.add_argument("--budget", type=float, default=config.MAX_BUDGET, help="LLM budget per bot per check match")
    cc.add_argument("--out", help="results folder (default results/<tid>/ or results/chatcheck-<tag>/)")
    cc.add_argument("--log-wait", type=float, default=60.0,
                    help="seconds to wait for the gateway to write a match's request logs")
    cc.add_argument("--seed", type=int)
    _clock_args(cc)
    cc.set_defaults(fn=cmd_chatcheck)

    rl = sub.add_parser("release", help="release a played tournament's games to the practice kit (arena-lite)")
    rl.add_argument("tid", nargs="?", help="a finished tournament: all the games of its pool are released")
    rl.add_argument("--games", help="release these game ids instead (comma-separated)")
    rl.add_argument("--undo", action="store_true", help="withdraw the games instead of releasing them")
    rl.add_argument("--list", action="store_true", help="show what is released")
    rl.add_argument("--force", action="store_true", help="also for an unfinished tournament or reserved games")
    rl.set_defaults(fn=cmd_release_games)

    eg = sub.add_parser("egress", help="what the bots reached on the internet (egress proxy log, per team)")
    eg.add_argument("--team", help="one team: every host it contacted")
    eg.add_argument("--blocked", action="store_true", help="only blocked attempts (model services, private addresses)")
    eg.add_argument("--log", help="log file (default platform/infra/egress/logs/egress.jsonl)")
    eg.add_argument("--teams", help="teams file (default platform/teams.json)")
    eg.add_argument("--json", action="store_true")
    eg.set_defaults(fn=cmd_egress)

    im = sub.add_parser("immutable", help="add an immutable tag rule to a Harbor project")
    im.add_argument("project")
    im.add_argument("--pattern", default="t*")
    im.set_defaults(fn=cmd_immutable)
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args) or 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except (RuntimeError, KeyError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

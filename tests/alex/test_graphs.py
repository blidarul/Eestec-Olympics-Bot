"""P2 tools: grid_bfs, grid_astar, grid_flood_fill, grid_components, graph_*, board_lines."""
import itertools
import json
import random
import time

import pytest

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

GRAPH_TOOLS = ["grid_bfs", "grid_astar", "grid_flood_fill", "grid_components", "graph_shortest_path",
               "graph_reachable", "graph_topo_sort", "graph_components", "graph_dfs_order", "board_lines"]


def ok(name, args):
    r = catalog.call(name, args)
    assert r["ok"], r
    return r["result"]


def bad(name, args):
    r = catalog.call(name, args)
    assert r["ok"] is False, r
    return r["error"]


def test_all_registered_and_model_callable():
    names = {s.name for s in catalog.list_tools(model_callable=True)}
    assert set(GRAPH_TOOLS) <= names
    exported = {t["function"]["name"] for t in catalog.openai_tools()}
    assert set(GRAPH_TOOLS) <= exported
    for t in catalog.openai_tools(GRAPH_TOOLS):
        json.dumps(t)
        assert t["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------- grid_bfs

MAZE = ["S..#",
        ".#..",
        "...E"]


def test_bfs_path_and_first_step():
    r = ok("grid_bfs", {"grid": MAZE, "start": [0, 0], "goal": [2, 3], "blocked": "#"})
    assert r["reachable"] and r["length"] == 5
    assert r["path"][0] == [0, 0] and r["path"][-1] == [2, 3]
    assert r["first_step"] in ("down", "right")
    assert len(r["directions"]) == 5
    # path is made of adjacent passable cells
    for (a, b), (c, d) in zip(r["path"], r["path"][1:]):
        assert abs(a - c) + abs(b - d) == 1 and MAZE[c][d] != "#"


def test_bfs_diagonal_shorter():
    r4 = ok("grid_bfs", {"grid": ["...", "...", "..."], "start": [0, 0], "goal": [2, 2]})
    r8 = ok("grid_bfs", {"grid": ["...", "...", "..."], "start": [0, 0], "goal": [2, 2], "diagonal": True})
    assert (r4["length"], r8["length"]) == (4, 2)
    assert r8["first_step"] == "down_right"


def test_bfs_unreachable_is_not_an_error():
    r = ok("grid_bfs", {"grid": ["S#E"], "start": [0, 0], "goal": [0, 2], "passable": "S.E"})
    assert r["reachable"] is False and r["path"] == [] and r["first_step"] is None


def test_bfs_same_cell_and_goal_marker_cell():
    r = ok("grid_bfs", {"grid": ["ab"], "start": [0, 0], "goal": [0, 0]})
    assert r["length"] == 0 and r["path"] == [[0, 0]] and r["first_step"] is None
    # goal char is not in passable but the goal cell itself may be entered
    r = ok("grid_bfs", {"grid": ["..G"], "start": [0, 0], "goal": [0, 2], "passable": "."})
    assert r["length"] == 2


def test_bfs_bad_input():
    assert "outside" in bad("grid_bfs", {"grid": MAZE, "start": [5, 0], "goal": [0, 0]})
    assert "same length" in bad("grid_bfs", {"grid": ["ab", "c"], "start": [0, 0], "goal": [0, 1]})
    assert bad("grid_bfs", {"grid": MAZE, "start": [0], "goal": [0, 0]})
    assert bad("grid_bfs", {"grid": MAZE, "start": "0,0", "goal": [0, 0]})


def test_bfs_long_path_is_truncated_but_length_is_exact():
    r = ok("grid_bfs", {"grid": ["." * 100] * 2, "start": [0, 0], "goal": [1, 99]})
    assert r["length"] == 100 and len(r["path"]) == 100 and r["path_truncated_cells"] == 1


def _brute_bfs(grid, start, goal, diag):
    h, w = len(grid), len(grid[0])
    deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)] + ([(-1, -1), (-1, 1), (1, -1), (1, 1)] if diag else [])
    dist = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for r, c in frontier:
            for dr, dc in deltas:
                n = (r + dr, c + dc)
                if 0 <= n[0] < h and 0 <= n[1] < w and n not in dist and (grid[n[0]][n[1]] != "#" or n == goal):
                    dist[n] = dist[(r, c)] + 1
                    nxt.append(n)
        frontier = nxt
    return dist.get(goal)


def test_bfs_and_astar_match_brute_force_on_random_grids():
    rng = random.Random(7)
    for _ in range(40):
        h, w = rng.randint(2, 8), rng.randint(2, 8)
        grid = ["".join(rng.choice("..#") for _ in range(w)) for _ in range(h)]
        s, g = (rng.randrange(h), rng.randrange(w)), (rng.randrange(h), rng.randrange(w))
        for diag in (False, True):
            want = _brute_bfs(grid, s, g, diag)
            r = ok("grid_bfs", {"grid": grid, "start": list(s), "goal": list(g), "blocked": "#", "diagonal": diag})
            assert (r["length"] if r["reachable"] else None) == want
        want4 = _brute_bfs(grid, s, g, False)
        a = ok("grid_astar", {"grid": grid, "start": list(s), "goal": list(g), "blocked": "#"})
        assert (a["length"] if a["reachable"] else None) == want4
        if a["reachable"]:
            assert a["cost"] == want4


# ---------------------------------------------------------------- grid_astar

def test_astar_costs_prefer_cheap_detour():
    grid = ["S~~E",
            "...."]
    r = ok("grid_astar", {"grid": grid, "start": [0, 0], "goal": [0, 3], "costs": {"~": 5}})
    assert r["cost"] == 5 and r["length"] == 5   # down, right x3, up: five cost-1 steps beat 1+5+5 and r["path"][1] == [1, 0]
    direct = ok("grid_astar", {"grid": grid, "start": [0, 0], "goal": [0, 3]})
    assert direct["length"] == 3 and direct["cost"] == 3


def test_astar_rejects_cost_below_one_and_unreachable():
    assert "cost" in bad("grid_astar", {"grid": ["S.E"], "start": [0, 0], "goal": [0, 2], "costs": {".": 0.5}})
    r = ok("grid_astar", {"grid": ["S#E"], "start": [0, 0], "goal": [0, 2], "blocked": "#"})
    assert r["reachable"] is False


# ---------------------------------------------------------------- flood fill / components

TERR = ["..XOO",
        ".XX.O",
        "XX..."]


def test_flood_fill_region_and_border():
    r = ok("grid_flood_fill", {"grid": TERR, "start": [0, 0], "passable": "."})
    assert r["size"] == 3 and r["bounding_box"] == [0, 0, 1, 1]
    assert set(r["border_chars"]) == {"X"}
    assert r["touches_grid_edge"] is True


def test_flood_fill_exact_region():
    r = ok("grid_flood_fill", {"grid": TERR, "start": [2, 2], "passable": "."})
    # (1,3) (2,2) (2,3) (2,4) are connected; (0,0)/(1,0)/(0,1)... are another region
    assert r["size"] == 4
    assert sorted(map(tuple, r["cells"])) == [(1, 3), (2, 2), (2, 3), (2, 4)]
    assert r["border_chars"].keys() == {"X", "O"}


def test_flood_fill_blocked_start_and_diagonal():
    r = ok("grid_flood_fill", {"grid": TERR, "start": [0, 2], "passable": "."})
    assert r["size"] == 0
    d = ok("grid_flood_fill", {"grid": ["X.", ".X"], "start": [0, 1], "passable": ".", "diagonal": True})
    n = ok("grid_flood_fill", {"grid": ["X.", ".X"], "start": [0, 1], "passable": "."})
    assert (d["size"], n["size"]) == (2, 1)


def test_components_sizes_and_liberties():
    r = ok("grid_components", {"grid": TERR, "chars": "X", "liberty_chars": "."})
    assert r["count"] == 1 and r["components"][0]["size"] == 5
    assert r["components"][0]["liberties"] == 4      # (0,1) (1,0) (2,2) (1,3)
    r2 = ok("grid_components", {"grid": TERR, "chars": "O"})
    assert r2["count"] == 1 and r2["components"][0]["size"] == 3
    r3 = ok("grid_components", {"grid": TERR, "chars": "XO"})
    assert r3["count"] == 1 and r3["total_cells"] == 8     # X and O touch at (0,2)-(0,3)


def test_components_liberties_brute_force():
    grid = ["X.X", ".X.", "X.X"]
    r = ok("grid_components", {"grid": grid, "chars": "X", "liberty_chars": "."})
    assert r["count"] == 5 and all(c["size"] == 1 for c in r["components"])
    libs = sorted(c["liberties"] for c in r["components"])
    assert libs == [2, 2, 2, 2, 4]
    r = ok("grid_components", {"grid": grid, "chars": "X", "liberty_chars": ".", "diagonal": True})
    assert r["count"] == 1 and r["components"][0]["size"] == 5 and r["components"][0]["liberties"] == 4


def test_components_none_found():
    r = ok("grid_components", {"grid": ["..."], "chars": "X"})
    assert r["count"] == 0 and r["largest"] == 0 and r["components"] == []


# ---------------------------------------------------------------- graph_shortest_path

def test_shortest_path_unweighted_adjacency():
    adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}
    r = ok("graph_shortest_path", {"adjacency": adj, "source": "a", "target": "d", "directed": True})
    assert r["method"] == "bfs" and r["cost"] == 2 and r["hops"] == 2 and r["path"][0] == "a" and r["path"][-1] == "d"
    assert r["next_node"] in ("b", "c")


def test_shortest_path_dijkstra_weighted():
    edges = [["a", "b", 1], ["b", "c", 1], ["a", "c", 5], ["c", "d", 1]]
    r = ok("graph_shortest_path", {"edges": edges, "source": "a", "target": "d"})
    assert r["method"] == "dijkstra" and r["cost"] == 3 and r["path"] == ["a", "b", "c", "d"]


def test_shortest_path_directed_and_unreachable_and_int_ids():
    r = ok("graph_shortest_path", {"edges": [[1, 2], [2, 3]], "source": 3, "target": 1, "directed": True})
    assert r["reachable"] is False
    r = ok("graph_shortest_path", {"edges": [[1, 2], [2, 3]], "source": 3, "target": 1})
    assert r["path"] == ["3", "2", "1"]
    r = ok("graph_shortest_path", {"edges": [["a", "b", 2]], "source": "a", "target": "a"})
    assert r["cost"] == 0 and r["path"] == ["a"] and r["next_node"] is None


def test_shortest_path_errors():
    assert "negative" in bad("graph_shortest_path", {"edges": [["a", "b", -1]], "source": "a", "target": "b"})
    assert "not in the graph" in bad("graph_shortest_path", {"edges": [["a", "b"]], "source": "a", "target": "z"})
    assert "adjacency" in bad("graph_shortest_path", {"source": "a", "target": "b"})
    assert bad("graph_shortest_path", {"edges": [["a"]], "source": "a", "target": "b"})


def test_dijkstra_matches_floyd_warshall():
    rng = random.Random(3)
    for _ in range(25):
        n = rng.randint(2, 7)
        edges = [[u, v, rng.randint(0, 9)] for u in range(n) for v in range(n) if u != v and rng.random() < 0.35]
        if not edges:
            continue
        inf = float("inf")
        d = [[0 if i == j else inf for j in range(n)] for i in range(n)]
        for u, v, w in edges:
            d[u][v] = min(d[u][v], w)
        for k, i, j in itertools.product(range(n), repeat=3):
            if d[i][k] + d[k][j] < d[i][j]:
                d[i][j] = d[i][k] + d[k][j]
        nodes = {x for e in edges for x in e[:2]}
        for s, t in itertools.product(nodes, repeat=2):
            r = ok("graph_shortest_path", {"edges": edges, "source": s, "target": t, "directed": True})
            if d[s][t] == inf:
                assert r["reachable"] is False
            else:
                assert r["cost"] == d[s][t]


# ---------------------------------------------------------------- reachable / topo / components / dfs

def test_reachable():
    r = ok("graph_reachable", {"edges": [["a", "b"], ["c", "d"]], "source": "a", "target": "d"})
    assert r["count"] == 2 and r["total_nodes"] == 4 and r["target_reachable"] is False and r["target_hops"] is None
    r = ok("graph_reachable", {"adjacency": {"a": ["b"], "b": ["c"], "c": []}, "source": "a", "target": "c", "directed": True})
    assert r["target_reachable"] is True and r["target_hops"] == 2
    r = ok("graph_reachable", {"adjacency": {"a": ["b"], "b": []}, "source": "b", "directed": True})
    assert r["nodes"] == ["b"]


def test_topo_sort_valid_order():
    edges = [["shirt", "tie"], ["tie", "jacket"], ["pants", "shoes"], ["pants", "belt"], ["belt", "jacket"]]
    r = ok("graph_topo_sort", {"edges": edges})
    assert r["has_cycle"] is False
    pos = {n: i for i, n in enumerate(r["order"])}
    assert len(pos) == 6 and all(pos[u] < pos[v] for u, v in edges)


def test_topo_sort_cycle_reported():
    r = ok("graph_topo_sort", {"edges": [["a", "b"], ["b", "c"], ["c", "a"], ["c", "d"]]})
    assert r["has_cycle"] is True and set(r["cycle"]) == {"a", "b", "c"}
    # the reported cycle follows real edges
    es = {("a", "b"), ("b", "c"), ("c", "a")}
    cyc = r["cycle"]
    assert all((cyc[i], cyc[(i + 1) % len(cyc)]) in es for i in range(len(cyc)))
    r = ok("graph_topo_sort", {"edges": [["x", "x"]]})
    assert r["has_cycle"] is True and r["cycle"] == ["x"]


def test_topo_sort_empty_and_isolated():
    r = ok("graph_topo_sort", {"adjacency": {"a": [], "b": []}})
    assert r["order"] == ["a", "b"]
    r = ok("graph_topo_sort", {"adjacency": {}})
    assert r["has_cycle"] is False and r["order"] == []


def test_graph_components():
    r = ok("graph_components", {"edges": [[1, 2], [2, 3], [4, 5]], "adjacency": {"9": []}})
    assert r["count"] == 3 and r["sizes"] == [3, 2, 1]
    assert sorted(r["components"][0]["nodes"]) == ["1", "2", "3"]
    # direction ignored
    r = ok("graph_components", {"edges": [["a", "b"], ["c", "b"]], "directed": True})
    assert r["count"] == 1


def test_dfs_order():
    adj = {"a": ["b", "c"], "b": ["d"], "c": [], "d": []}
    r = ok("graph_dfs_order", {"adjacency": adj, "source": "a", "directed": True})
    assert r["preorder"] == ["a", "b", "d", "c"] and r["postorder"] == ["d", "b", "c", "a"]
    r = ok("graph_dfs_order", {"edges": [["a", "b"], ["b", "a"], ["b", "c"]], "source": "a"})
    assert r["count"] == 3 and r["preorder"][0] == "a"


def test_graph_size_limits_and_deep_chain():
    big = [[i, i + 1] for i in range(4000)]
    r = ok("graph_dfs_order", {"edges": big, "source": 0, "directed": True})     # iterative: no recursion limit
    assert r["count"] == 4001 and r["lists_truncated"] == 3901
    assert bad("graph_reachable", {"edges": [[i, i + 1] for i in range(5001)], "source": 0})
    assert bad("graph_reachable", {"adjacency": {"a": "b"}, "source": "a"})


# ---------------------------------------------------------------- board_lines

TTT = ["XX.",
       "OO.",
       "..."]


def test_board_lines_tictactoe_wins_and_blocks():
    r = ok("board_lines", {"board": TTT, "k": 3, "players": ["X", "O"], "coord_style": "A1"})
    x, o = r["players"]["X"], r["players"]["O"]
    assert x["has_won"] is False and x["winning_moves"] == ["C1"]
    assert o["winning_moves"] == ["C2"]
    assert x["blocking_moves"] == ["C2"] and o["blocking_moves"] == ["C1"]
    assert x["open_lines_k_minus_1"] == 1


def test_board_lines_coord_styles():
    for style, want in (("rc", ["0,2"]), ("index", [2]), ("A1", ["C1"])):
        r = ok("board_lines", {"board": TTT, "k": 3, "players": ["X", "O"], "coord_style": style})
        assert r["players"]["X"]["winning_moves"] == want
    r = ok("board_lines", {"board": TTT, "k": 3, "players": ["X", "O"], "coord_style": "A1", "row_origin": "bottom"})
    assert r["players"]["X"]["winning_moves"] == ["C3"]
    assert "columns" in bad("board_lines", {"board": ["." * 27], "k": 3, "players": ["X"], "coord_style": "A1"})


def test_board_lines_win_detection_all_directions():
    cases = {
        "row": ["XXX", "...", "..."],
        "col": ["X..", "X..", "X.."],
        "diag": ["X..", ".X.", "..X"],
        "anti": ["..X", ".X.", "X.."],
    }
    for label, board in cases.items():
        r = ok("board_lines", {"board": board, "k": 3, "players": ["X", "O"]})
        assert r["players"]["X"]["has_won"] is True, label
        assert r["players"]["O"]["has_won"] is False, label


def test_board_lines_other_k_and_larger_board():
    board = ["......", ".XXX..", "..O...", "......", "......", "......"]
    r = ok("board_lines", {"board": board, "k": 4, "players": ["X", "O"], "coord_style": "rc"})
    x = r["players"]["X"]
    assert sorted(x["winning_moves"]) == ["1,0", "1,4"]
    assert x["open_lines_k_minus_1"] == 2
    # a window broken by an opposing stone is not an open line
    board = ["XXO..", ".....", ".....", ".....", "....."]
    r = ok("board_lines", {"board": board, "k": 3, "players": ["X", "O"]})
    assert r["players"]["X"]["winning_moves"] == [] and r["players"]["X"]["open_lines_k_minus_1"] == 0


def test_board_lines_k_minus_2_and_empty_board():
    r = ok("board_lines", {"board": ["X....", ".....", "....."], "k": 4, "players": ["X", "O"]})
    assert r["players"]["X"]["open_lines_k_minus_2"] == 0     # one stone only, k-2 = 2
    r = ok("board_lines", {"board": ["XX..", "....", "...."], "k": 4, "players": ["X", "O"]})
    assert r["players"]["X"]["open_lines_k_minus_2"] == 1
    r = ok("board_lines", {"board": ["...", "...", "..."], "k": 3, "players": ["X", "O"]})
    assert r["players"]["X"]["winning_moves"] == [] and r["empty_cells"] == 9


def test_board_lines_custom_empty_and_three_players():
    r = ok("board_lines", {"board": ["AA_", "BB_", "CC_"], "k": 3, "players": ["A", "B", "C"], "empty": "_"})
    for p in "ABC":
        assert r["players"][p]["winning_moves"] == ["%d,2" % "ABC".index(p)]
    assert r["players"]["A"]["blocking_moves"] == ["1,2", "2,2"]


def test_board_lines_errors():
    assert "k=" in bad("board_lines", {"board": ["..", ".."], "k": 3, "players": ["X"]})
    assert "same length" in bad("board_lines", {"board": ["..", "."], "k": 2, "players": ["X"]})
    assert bad("board_lines", {"board": ["..", ".."], "k": 2, "players": ["X", "X"]})
    assert bad("board_lines", {"board": ["..", ".."], "k": 2, "players": ["X"], "empty": "X"})
    assert bad("board_lines", {"board": ["." * 31] * 2, "k": 3, "players": ["X"]})


def test_board_lines_brute_force_winning_moves():
    rng = random.Random(11)
    for _ in range(30):
        n, k = rng.randint(3, 6), rng.randint(3, 4)
        if k > n:
            continue
        board = ["".join(rng.choice("XO..") for _ in range(n)) for _ in range(n)]

        def has_line(b, p):
            for r, c in itertools.product(range(n), repeat=2):
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    cells = [(r + dr * i, c + dc * i) for i in range(k)]
                    if all(0 <= a < n and 0 <= bb < n and b[a][bb] == p for a, bb in cells):
                        return True
            return False

        res = ok("board_lines", {"board": board, "k": k, "players": ["X", "O"]})
        for p in "XO":
            if has_line(board, p):
                assert res["players"][p]["has_won"]
                continue
            want = []
            for r, c in itertools.product(range(n), repeat=2):
                if board[r][c] == ".":
                    b2 = [list(row) for row in board]
                    b2[r][c] = p
                    if has_line(b2, p):
                        want.append("%d,%d" % (r, c))
            assert sorted(res["players"][p]["winning_moves"]) == sorted(want)
            assert not res["players"][p]["has_won"]


# ---------------------------------------------------------------- deadline and robustness

def test_deadline_is_respected_on_big_grid():
    grid = ["." * 100] * 100
    t0 = time.monotonic()
    r = catalog.call("grid_components", {"grid": grid, "chars": "."}, deadline=time.monotonic() + 2)
    assert r["ok"] and time.monotonic() - t0 < 2.5
    t0 = time.monotonic()
    r = catalog.call("grid_bfs", {"grid": grid, "start": [0, 0], "goal": [99, 99], "diagonal": True}, deadline=time.monotonic() + 2)
    assert r["ok"] and r["result"]["length"] == 99 and time.monotonic() - t0 < 2.5


def test_expired_deadline_returns_error_not_exception():
    r = catalog.call("grid_components", {"grid": ["." * 100] * 100, "chars": "."}, deadline=time.monotonic() + 1e-4)
    assert r["ok"] is False or r["ok"] is True       # either answer is fine, it must just return
    r = catalog.call("grid_bfs", {"grid": ["..."], "start": [0, 0], "goal": [0, 2]}, deadline=time.monotonic() - 1)
    assert r["ok"] is False


def test_results_fit_4kb_on_big_inputs():
    grid = ["." * 100] * 100
    for name, args in (("grid_flood_fill", {"grid": grid, "start": [0, 0]}),
                       ("grid_components", {"grid": ["".join("X." [(r + c) % 2] for c in range(100)) for r in range(100)], "chars": "X", "liberty_chars": "."}),
                       ("grid_bfs", {"grid": grid, "start": [0, 0], "goal": [99, 99]}),
                       ("graph_components", {"edges": [[i, i + 1000] for i in range(1000)]})):
        r = catalog.call(name, args)
        assert r["ok"], r
        assert "truncated" not in r["result"] or r["result"].get("truncated") is not True, name
        assert len(json.dumps(r["result"])) <= 4096, name


def test_args_as_json_string():
    r = catalog.call("grid_bfs", json.dumps({"grid": MAZE, "start": [0, 0], "goal": [2, 3], "blocked": "#"}))
    assert r["ok"] and r["result"]["length"] == 5

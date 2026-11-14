"""Grid, graph and board-line tools (TOOLS_PLAN.md phase P2).

General tools (no game names, rule 10.7): plain data in, plain data out, stdlib only, no eval.
Grids are lists of equal-length strings (one char per cell); cells are [row, col], zero-based,
row 0 is the top row. Graph node ids are compared as text ("1" and 1 are the same node).
"""
import heapq
import time
from collections import deque

from solvers.catalog import ToolError, ToolSpec, register

MAX_DIM = 100          # grid rows / columns
MAX_CELLS = 10000
MAX_EDGES = 5000
MAX_NODES = 5000
LIST_CAP = 100         # items listed in one result (4 KB result limit)
_TICK = 512            # loop iterations between deadline checks

# direction name -> (d_row, d_col); orthogonal first so BFS ties prefer them
_ORTHO = (("up", -1, 0), ("down", 1, 0), ("left", 0, -1), ("right", 0, 1))
_DIAG = (("up_left", -1, -1), ("up_right", -1, 1), ("down_left", 1, -1), ("down_right", 1, 1))


class _Clock:
    """Cheap deadline guard for hot loops."""

    def __init__(self, deadline):
        self.deadline = deadline
        self.n = 0

    def tick(self):
        self.n += 1
        if self.n % _TICK == 0 and time.monotonic() > self.deadline:
            raise ToolError("deadline exceeded")


def _cap(items, n=LIST_CAP):
    return list(items[:n]), max(0, len(items) - n)


# ---------------------------------------------------------------- grid helpers

_GRID_PROPS = {
    "grid": {"type": "array", "minItems": 1, "maxItems": MAX_DIM,
             "items": {"type": "string", "minLength": 1, "maxLength": MAX_DIM},
             "description": "rows of equal length, one character per cell"},
    "passable": {"type": "string", "maxLength": 64,
                 "description": "characters you can walk on (each character of this string); if omitted every cell is passable except 'blocked'"},
    "blocked": {"type": "string", "maxLength": 64,
                "description": "characters you cannot walk on; use passable OR blocked (or neither: all cells passable)"},
}
_CELL = {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "integer", "minimum": 0, "maximum": MAX_DIM},
         "description": "[row, col], zero-based, row 0 = top row"}
_DIAGONAL = {"type": "boolean", "description": "allow diagonal moves (8 neighbours); default false (4 neighbours)"}


class _Grid:
    def __init__(self, args):
        rows = args["grid"]
        self.rows = rows
        self.h = len(rows)
        self.w = len(rows[0])
        if any(len(r) != self.w for r in rows):
            raise ToolError("grid rows must all have the same length")
        if self.h * self.w > MAX_CELLS:
            raise ToolError("grid too large (max %d cells)" % MAX_CELLS)
        passable, blocked = args.get("passable"), args.get("blocked")
        self.passable = set(passable) if passable is not None else None
        self.blocked = set(blocked) if blocked is not None else set()
        self.dirs = _ORTHO + (_DIAG if args.get("diagonal") else ())

    def cell(self, value, label):
        r, c = value
        if not (0 <= r < self.h and 0 <= c < self.w):
            raise ToolError("%s %s is outside the %dx%d grid" % (label, [r, c], self.h, self.w))
        return (r, c)

    def ch(self, r, c):
        return self.rows[r][c]

    def ok(self, r, c):
        ch = self.rows[r][c]
        if ch in self.blocked:
            return False
        return self.passable is None or ch in self.passable

    def neighbours(self, r, c):
        for name, dr, dc in self.dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.h and 0 <= nc < self.w:
                yield name, nr, nc


def _path_result(path, dirs, cost=None):
    shown, more = _cap(path)
    res = {"reachable": True, "length": len(path) - 1, "path": [list(p) for p in shown],
           "first_step": dirs[0] if dirs else None, "directions": dirs[:LIST_CAP]}
    if more:
        res["path_truncated_cells"] = more
    if cost is not None:
        res["cost"] = cost
    return res


# ---------------------------------------------------------------- grid_bfs

def grid_bfs(args, deadline):
    g = _Grid(args)
    start = g.cell(args["start"], "start")
    goal = g.cell(args["goal"], "goal")
    clock = _Clock(deadline)
    if start == goal:
        res = _path_result([start], [])
        res["explain"] = "Start and goal are the same cell."
        return res
    parent = {start: None}
    q = deque([start])
    found = False
    while q and not found:
        r, c = q.popleft()
        for name, nr, nc in g.neighbours(r, c):
            clock.tick()
            n = (nr, nc)
            if n in parent:
                continue
            if n != goal and not g.ok(nr, nc):   # the goal cell itself may be a marker char
                continue
            parent[n] = ((r, c), name)
            if n == goal:
                found = True
                break
            q.append(n)
    if not found:
        return {"reachable": False, "explored_cells": len(parent), "length": None, "path": [],
                "first_step": None, "explain": "Goal %s is not reachable from %s." % (list(goal), list(start))}
    path, dirs = [goal], []
    cur = goal
    while parent[cur] is not None:
        prev, name = parent[cur]
        dirs.append(name)
        path.append(prev)
        cur = prev
    path.reverse()
    dirs.reverse()
    res = _path_result(path, dirs)
    res["explain"] = "Shortest path %s -> %s is %d steps, first step %s." % (list(start), list(goal), len(dirs), dirs[0])
    return res


register(ToolSpec(
    name="grid_bfs",
    summary="Shortest path between two cells of a character grid (4 or 8 neighbours): path, length and the first step direction; reports unreachable instead of failing.",
    params={"type": "object",
            "properties": dict(_GRID_PROPS, start=_CELL, goal=_CELL, diagonal=_DIAGONAL),
            "required": ["grid", "start", "goal"]},
    fn=grid_bfs, families=("think_ahead",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- grid_astar

def grid_astar(args, deadline):
    g = _Grid(args)
    start = g.cell(args["start"], "start")
    goal = g.cell(args["goal"], "goal")
    costs = args.get("costs") or {}
    if not isinstance(costs, dict):
        raise ToolError("costs must be an object {character: cost}")
    for k, v in costs.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 1 or v > 1e6:
            raise ToolError("cost of %r must be a number between 1 and 1000000 (the Manhattan heuristic needs >= 1)" % k)
    clock = _Clock(deadline)

    def h(p):
        return abs(p[0] - goal[0]) + abs(p[1] - goal[1])

    best = {start: 0}
    parent = {start: None}
    heap = [(h(start), 0, 0, start)]
    count = 0
    expanded = 0
    done = set()
    while heap:
        _, gc, _, cur = heapq.heappop(heap)
        if cur in done:
            continue
        done.add(cur)
        expanded += 1
        if cur == goal:
            break
        r, c = cur
        for name, dr, dc in _ORTHO:               # Manhattan heuristic: 4 neighbours only
            nr, nc = r + dr, c + dc
            clock.tick()
            if not (0 <= nr < g.h and 0 <= nc < g.w):
                continue
            n = (nr, nc)
            if n != goal and not g.ok(nr, nc):
                continue
            ng = gc + costs.get(g.ch(nr, nc), 1)
            if ng < best.get(n, float("inf")):
                best[n] = ng
                parent[n] = (cur, name)
                count += 1
                heapq.heappush(heap, (ng + h(n), ng, count, n))
    if goal not in done:
        return {"reachable": False, "expanded_cells": expanded, "length": None, "path": [], "first_step": None,
                "explain": "Goal %s is not reachable from %s." % (list(goal), list(start))}
    path, dirs = [goal], []
    cur = goal
    while parent[cur] is not None:
        prev, name = parent[cur]
        dirs.append(name)
        path.append(prev)
        cur = prev
    path.reverse()
    dirs.reverse()
    res = _path_result(path, dirs, cost=best[goal])
    res["expanded_cells"] = expanded
    res["explain"] = "Cheapest path %s -> %s costs %s over %d steps%s." % (
        list(start), list(goal), best[goal], len(dirs), (", first step " + dirs[0]) if dirs else "")
    return res


register(ToolSpec(
    name="grid_astar",
    summary="A* (Manhattan heuristic, 4 neighbours) on a character grid; optional per-character entering costs (each >= 1): cheapest path, its cost and the first step.",
    params={"type": "object",
            "properties": dict(_GRID_PROPS, start=_CELL, goal=_CELL,
                               costs={"type": "object", "description": "optional {character: cost of entering that cell}, cost >= 1, default 1"}),
            "required": ["grid", "start", "goal"]},
    fn=grid_astar, families=("think_ahead",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- grid_flood_fill / grid_components

def _region(g, start, member, clock):
    """Cells connected to start through cells for which member(r, c) is true (start included)."""
    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        for _, nr, nc in g.neighbours(r, c):
            clock.tick()
            n = (nr, nc)
            if n not in seen and member(nr, nc):
                seen.add(n)
                q.append(n)
    return seen


def _bbox(cells):
    rs = [p[0] for p in cells]
    cs = [p[1] for p in cells]
    return [min(rs), min(cs), max(rs), max(cs)]


def grid_flood_fill(args, deadline):
    g = _Grid(args)
    start = g.cell(args["start"], "start")
    clock = _Clock(deadline)
    if not g.ok(*start):
        return {"size": 0, "cells": [], "explain": "Start cell %s ('%s') is not passable: empty region." % (list(start), g.ch(*start))}
    cells = _region(g, start, g.ok, clock)
    border = {}
    for r, c in cells:
        for _, nr, nc in g.neighbours(r, c):
            if (nr, nc) not in cells:
                border[g.ch(nr, nc)] = border.get(g.ch(nr, nc), 0) + 1
    edge = any(r in (0, g.h - 1) or c in (0, g.w - 1) for r, c in cells)
    ordered = sorted(cells)
    shown, more = _cap(ordered)
    res = {"size": len(cells), "cells": [list(p) for p in shown], "bounding_box": _bbox(cells),
           "touches_grid_edge": edge, "border_chars": dict(sorted(border.items())[:20])}
    if more:
        res["cells_truncated"] = more
    res["explain"] = "Region from %s has %d cells; bordered by %s." % (
        list(start), len(cells), ", ".join("%r x%d" % kv for kv in sorted(border.items())[:6]) or "nothing (grid edge only)")
    return res


register(ToolSpec(
    name="grid_flood_fill",
    summary="Connected region of passable cells from a start cell: size, cells, bounding box, and which characters border it (territory / group checks).",
    params={"type": "object",
            "properties": dict(_GRID_PROPS, start=_CELL, diagonal=_DIAGONAL),
            "required": ["grid", "start"]},
    fn=grid_flood_fill, families=("think_ahead",), model_callable=True, max_ms=1500))


def grid_components(args, deadline):
    g = _Grid(args)
    chars = set(args["chars"])
    liberty = set(args.get("liberty_chars") or "")
    clock = _Clock(deadline)

    def member(r, c):
        return g.ch(r, c) in chars

    seen = set()
    comps = []
    for r in range(g.h):
        for c in range(g.w):
            if (r, c) in seen or not member(r, c):
                continue
            cells = _region(g, (r, c), member, clock)
            seen |= cells
            entry = {"size": len(cells), "first_cell": [r, c], "char": g.ch(r, c), "bounding_box": _bbox(cells)}
            if liberty:
                libs = set()
                for cr, cc in cells:
                    for _, nr, nc in g.neighbours(cr, cc):
                        if g.ch(nr, nc) in liberty:
                            libs.add((nr, nc))
                entry["liberties"] = len(libs)
            comps.append(entry)
    comps.sort(key=lambda e: (-e["size"], e["first_cell"]))
    shown, more = _cap(comps, 25)
    res = {"count": len(comps), "total_cells": sum(e["size"] for e in comps),
           "largest": comps[0]["size"] if comps else 0, "components": shown}
    if more:
        res["components_truncated"] = more
    res["explain"] = "%d component(s) of %r, largest %d cells." % (len(comps), "".join(sorted(chars)), res["largest"])
    return res


register(ToolSpec(
    name="grid_components",
    summary="All connected groups of cells whose character is in 'chars': count, sizes, bounding boxes and (optional) liberties = distinct neighbouring cells with 'liberty_chars'.",
    params={"type": "object",
            "properties": dict(_GRID_PROPS, diagonal=_DIAGONAL,
                               chars={"type": "string", "minLength": 1, "maxLength": 32,
                                      "description": "characters that form the class (e.g. 'X' for one player's stones, '.' for empty cells)"},
                               liberty_chars={"type": "string", "maxLength": 32,
                                              "description": "optional: characters counted as liberties (usually the empty cell character)"}),
            "required": ["grid", "chars"]},
    fn=grid_components, families=("think_ahead",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- graph helpers

_NODE = {"type": ["string", "integer"]}
_GRAPH_PROPS = {
    "adjacency": {"type": "object", "description": "{node: [neighbor, ...]}; node ids are compared as text"},
    "edges": {"type": "array", "maxItems": MAX_EDGES,
              "items": {"type": "array", "minItems": 2, "maxItems": 3},
              "description": "list of [u, v] or [u, v, weight]; weight defaults to 1 and must be >= 0"},
    "directed": {"type": "boolean", "description": "edges only go u -> v; default false (every edge works both ways)"},
}


def _node(x, label="node"):
    if isinstance(x, bool) or not isinstance(x, (str, int)):
        raise ToolError("%s ids must be strings or integers" % label)
    return str(x)


class _Graph:
    def __init__(self, args, directed=None):
        self.directed = args.get("directed", False) if directed is None else directed
        self.adj = {}          # node -> list of (neighbor, weight), insertion ordered
        self.weighted = False
        self._n_edges = 0
        adjacency, edges = args.get("adjacency"), args.get("edges")
        if adjacency is None and edges is None:
            raise ToolError("give 'adjacency' or 'edges'")
        if adjacency is not None:
            if not isinstance(adjacency, dict):
                raise ToolError("adjacency must be an object {node: [neighbors]}")
            for u, nbrs in adjacency.items():
                if not isinstance(nbrs, list):
                    raise ToolError("adjacency[%s] must be a list" % u)
                self._touch(_node(u))
                for v in nbrs:
                    self._edge(_node(u), _node(v), 1)
        for e in edges or ():
            if not isinstance(e, list) or not 2 <= len(e) <= 3:
                raise ToolError("each edge must be [u, v] or [u, v, weight]")
            w = 1
            if len(e) == 3:
                w = e[2]
                if isinstance(w, bool) or not isinstance(w, (int, float)) or w != w:
                    raise ToolError("edge weight must be a number")
                if w < 0:
                    raise ToolError("negative edge weight %s is not supported" % w)
                if w != 1:
                    self.weighted = True
            self._edge(_node(e[0]), _node(e[1]), w)
        if len(self.adj) > MAX_NODES:
            raise ToolError("graph too large (max %d nodes)" % MAX_NODES)

    def _touch(self, u):
        if u not in self.adj:
            self.adj[u] = []

    def _edge(self, u, v, w):
        self._n_edges += 1
        if self._n_edges > MAX_EDGES * 2:
            raise ToolError("graph too large (max %d edges)" % MAX_EDGES)
        self._touch(u)
        self._touch(v)
        self.adj[u].append((v, w))
        if not self.directed:
            self.adj[v].append((u, w))

    def need(self, x, label):
        n = _node(x, label)
        if n not in self.adj:
            raise ToolError("%s %r is not in the graph" % (label, n))
        return n


def _bounded_nodes(nodes):
    shown, more = _cap(list(nodes))
    return shown, more


# ---------------------------------------------------------------- graph_shortest_path

def graph_shortest_path(args, deadline):
    gr = _Graph(args)
    src = gr.need(args["source"], "source")
    dst = gr.need(args["target"], "target")
    clock = _Clock(deadline)
    dist = {src: 0}
    parent = {src: None}
    if not gr.weighted:                        # BFS: every edge costs 1 (weight 1 edges included)
        q = deque([src])
        while q and dst not in parent:
            u = q.popleft()
            for v, _ in gr.adj[u]:
                clock.tick()
                if v not in parent:
                    parent[v] = u
                    dist[v] = dist[u] + 1
                    q.append(v)
        method = "bfs"
    else:                                      # Dijkstra
        heap = [(0, 0, src)]
        order = 0
        done = set()
        while heap:
            d, _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u == dst:
                break
            for v, w in gr.adj[u]:
                clock.tick()
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    parent[v] = u
                    order += 1
                    heapq.heappush(heap, (nd, order, v))
        method = "dijkstra"
    if dst not in parent or (method == "dijkstra" and dst not in done):
        return {"reachable": False, "method": method, "path": [], "cost": None,
                "explain": "%s is not reachable from %s." % (dst, src)}
    path = [dst]
    while parent[path[-1]] is not None:
        path.append(parent[path[-1]])
    path.reverse()
    shown, more = _cap(path)
    res = {"reachable": True, "method": method, "cost": dist[dst], "hops": len(path) - 1, "path": shown,
           "next_node": path[1] if len(path) > 1 else None}
    if more:
        res["path_truncated_nodes"] = more
    res["explain"] = "%s path %s -> %s: cost %s over %d hop(s)." % (method, src, dst, dist[dst], len(path) - 1)
    return res


register(ToolSpec(
    name="graph_shortest_path",
    summary="Shortest path in a graph given as adjacency lists or [u, v, weight] edges (BFS when unweighted, Dijkstra when weighted): path, cost, next node; reports unreachable.",
    params={"type": "object",
            "properties": dict(_GRAPH_PROPS, source=_NODE, target=_NODE),
            "required": ["source", "target"]},
    fn=graph_shortest_path, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- graph_reachable

def graph_reachable(args, deadline):
    gr = _Graph(args)
    src = gr.need(args["source"], "source")
    clock = _Clock(deadline)
    hops = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        for v, _ in gr.adj[u]:
            clock.tick()
            if v not in hops:
                hops[v] = hops[u] + 1
                q.append(v)
    shown, more = _bounded_nodes(hops)
    res = {"count": len(hops), "total_nodes": len(gr.adj), "nodes": shown}
    if more:
        res["nodes_truncated"] = more
    text = "%d of %d node(s) reachable from %s" % (len(hops), len(gr.adj), src)
    if args.get("target") is not None:
        t = gr.need(args["target"], "target")
        res["target_reachable"] = t in hops
        res["target_hops"] = hops.get(t)
        text += "; %s is %s" % (t, "reachable in %d hop(s)" % hops[t] if t in hops else "NOT reachable")
    res["explain"] = text + "."
    return res


register(ToolSpec(
    name="graph_reachable",
    summary="All nodes reachable from a source (optionally: is 'target' reachable and in how many hops).",
    params={"type": "object",
            "properties": dict(_GRAPH_PROPS, source=_NODE, target=_NODE),
            "required": ["source"]},
    fn=graph_reachable, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- graph_topo_sort

def graph_topo_sort(args, deadline):
    gr = _Graph(args, directed=True)           # a topological order only makes sense for directed edges
    clock = _Clock(deadline)
    index = {n: i for i, n in enumerate(gr.adj)}
    indeg = {n: 0 for n in gr.adj}
    for u in gr.adj:
        for v, _ in gr.adj[u]:
            indeg[v] += 1
    heap = [(index[n], n) for n, d in indeg.items() if d == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, u = heapq.heappop(heap)
        order.append(u)
        for v, _ in gr.adj[u]:
            clock.tick()
            indeg[v] -= 1
            if indeg[v] == 0:
                heapq.heappush(heap, (index[v], v))
    if len(order) == len(gr.adj):
        shown, more = _cap(order)
        res = {"has_cycle": False, "order": shown}
        if more:
            res["order_truncated"] = more
        res["explain"] = "Topological order of %d node(s); first: %s." % (len(order), order[0] if order else "-")
        return res
    left = [n for n in gr.adj if indeg[n] > 0]
    leftset = set(left)
    pred = {}
    for u in left:
        for v, _ in gr.adj[u]:
            if v in leftset:
                pred.setdefault(v, u)
    cur, seen = left[0], []
    while cur not in seen:                     # every leftover node has a leftover predecessor
        seen.append(cur)
        cur = pred[cur]
    cycle = seen[seen.index(cur):][::-1]
    shown, more = _cap(order)
    cyc, _ = _cap(cycle, 30)
    res = {"has_cycle": True, "cycle": cyc, "partial_order": shown, "blocked_nodes": len(left)}
    if more:
        res["order_truncated"] = more
    res["explain"] = "Cycle found: %s; %d node(s) cannot be ordered." % (" -> ".join(cyc + cyc[:1]), len(left))
    return res


register(ToolSpec(
    name="graph_topo_sort",
    summary="Topological order of a directed graph (dependencies, prerequisites); reports one concrete cycle if there is none. Edges are always read as u -> v.",
    params={"type": "object", "properties": {k: v for k, v in _GRAPH_PROPS.items() if k != "directed"}},
    fn=graph_topo_sort, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- graph_components

def graph_components(args, deadline):
    gr = _Graph(args, directed=True)           # direction is ignored: union-find joins both ends
    clock = _Clock(deadline)
    parent = {n: n for n in gr.adj}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for u in gr.adj:
        for v, _ in gr.adj[u]:
            clock.tick()
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[rv] = ru
    groups = {}
    for n in gr.adj:
        groups.setdefault(find(n), []).append(n)
    comps = sorted(groups.values(), key=lambda m: (-len(m), m[0]))
    shown_c, more_c = _cap(comps, 20)
    out = []
    for m in shown_c:
        nodes, more = _cap(m, 30)
        e = {"size": len(m), "nodes": nodes}
        if more:
            e["nodes_truncated"] = more
        out.append(e)
    res = {"count": len(comps), "sizes": [len(m) for m in comps[:50]], "components": out}
    if more_c:
        res["components_truncated"] = more_c
    res["explain"] = "%d connected component(s) (edge direction ignored), largest has %d node(s)." % (
        len(comps), len(comps[0]) if comps else 0)
    return res


register(ToolSpec(
    name="graph_components",
    summary="Connected components of a graph (union-find, edge direction ignored): count, sizes and members.",
    params={"type": "object", "properties": {k: v for k, v in _GRAPH_PROPS.items() if k != "directed"}},
    fn=graph_components, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- graph_dfs_order

def graph_dfs_order(args, deadline):
    gr = _Graph(args)
    src = gr.need(args["source"], "source")
    clock = _Clock(deadline)
    pre, post, seen = [], [], {src}
    stack = [(src, iter(gr.adj[src]))]
    pre.append(src)
    while stack:
        u, it = stack[-1]
        for v, _ in it:
            clock.tick()
            if v not in seen:
                seen.add(v)
                pre.append(v)
                stack.append((v, iter(gr.adj[v])))
                break
        else:
            post.append(u)
            stack.pop()
    shown_pre, more = _cap(pre)
    shown_post, _ = _cap(post)
    res = {"count": len(pre), "preorder": shown_pre, "postorder": shown_post}
    if more:
        res["lists_truncated"] = more
    res["explain"] = "Depth-first from %s visits %d node(s) (neighbors in the given order)." % (src, len(pre))
    return res


register(ToolSpec(
    name="graph_dfs_order",
    summary="Depth-first visit order (preorder and postorder) from a source, neighbors taken in the order given.",
    params={"type": "object", "properties": dict(_GRAPH_PROPS, source=_NODE), "required": ["source"]},
    fn=graph_dfs_order, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- board_lines

MAX_BOARD = 30


def _cell_namer(style, rows, cols, row_origin):
    if style == "A1":
        if cols > 26:
            raise ToolError("coord_style A1 supports at most 26 columns")

        def name(r, c):
            return "%s%d" % (chr(65 + c), (r + 1) if row_origin == "top" else (rows - r))
    elif style == "index":
        def name(r, c):
            return r * cols + c
    else:
        def name(r, c):
            return "%d,%d" % (r, c)
    return name


def _windows(rows, cols, k):
    """All straight windows of k consecutive cells: rows, columns and both diagonals."""
    out = []
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                er, ec = r + dr * (k - 1), c + dc * (k - 1)
                if 0 <= er < rows and 0 <= ec < cols:
                    out.append(tuple((r + dr * i, c + dc * i) for i in range(k)))
    return out


def board_lines(args, deadline):
    board = args["board"]
    rows, cols = len(board), len(board[0])
    if any(len(r) != cols for r in board):
        raise ToolError("board rows must all have the same length")
    if rows > MAX_BOARD or cols > MAX_BOARD:
        raise ToolError("board too large (max %dx%d)" % (MAX_BOARD, MAX_BOARD))
    k = args["k"]
    if k > max(rows, cols):
        raise ToolError("k=%d does not fit on a %dx%d board" % (k, rows, cols))
    players = args["players"]
    if len(set(players)) != len(players):
        raise ToolError("players must be distinct")
    empty = args.get("empty", ".")
    if any(len(s) != 1 for s in players) or len(empty) != 1:
        raise ToolError("player symbols and 'empty' must be single characters")
    if empty in players:
        raise ToolError("'empty' must differ from the player symbols")
    name = _cell_namer(args.get("coord_style", "rc"), rows, cols, args.get("row_origin", "top"))
    wins = _windows(rows, cols, k)
    clock = _Clock(deadline)
    # per window: (count of each player's symbols, empties, other chars) classified once
    info = []
    for w in wins:
        clock.tick()
        chars = [board[r][c] for r, c in w]
        info.append((w, chars))
    won, win_cells, near1, near2 = {}, {}, {}, {}
    for p in players:
        won[p], near1[p], near2[p] = False, 0, 0
        win_cells[p] = {}
        for w, chars in info:
            n_p = chars.count(p)
            n_e = chars.count(empty)
            if n_p == k:
                won[p] = True
            elif n_p + n_e == k:               # window not spoiled by another symbol
                if n_p == k - 1:
                    near1[p] += 1
                    cell = w[chars.index(empty)]
                    win_cells[p][cell] = True
                elif n_p == k - 2 and k >= 3:
                    near2[p] += 1
    result = {"k": k, "board_size": [rows, cols], "empty_cells": sum(r.count(empty) for r in board), "players": {}}
    lines = []
    for p in players:
        mine = sorted(win_cells[p])
        blocks = sorted({cell for q in players if q != p for cell in win_cells[q]})
        w_names, w_more = _cap([name(*c) for c in mine], 40)
        b_names, b_more = _cap([name(*c) for c in blocks], 40)
        entry = {"has_won": won[p], "winning_moves": w_names, "blocking_moves": b_names,
                 "open_lines_k_minus_1": near1[p], "open_lines_k_minus_2": near2[p]}
        if w_more:
            entry["winning_moves_truncated"] = w_more
        if b_more:
            entry["blocking_moves_truncated"] = b_more
        result["players"][p] = entry
        lines.append("%s: %s%s, %d line(s) one short, %d two short; must block: %s" % (
            p, "WON" if won[p] else "no win yet", (" (win at %s)" % ", ".join(map(str, w_names[:6]))) if w_names else "",
            near1[p], near2[p], ", ".join(map(str, b_names[:6])) or "none"))
    result["explain"] = " | ".join(lines)
    return result


register(ToolSpec(
    name="board_lines",
    summary="k-in-a-row analysis of any board (rows, columns, both diagonals): per player has_won, immediate winning moves, cells that block the opponent's immediate win, counts of open lines one and two short of k.",
    params={"type": "object",
            "properties": {
                "board": {"type": "array", "minItems": 1, "maxItems": MAX_BOARD,
                          "items": {"type": "string", "minLength": 1, "maxLength": MAX_BOARD},
                          "description": "rows of equal length, one character per cell, top row first"},
                "k": {"type": "integer", "minimum": 2, "maximum": MAX_BOARD, "description": "length of a winning line"},
                "players": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string", "minLength": 1, "maxLength": 1},
                            "description": "player symbols, e.g. ['X','O']"},
                "empty": {"type": "string", "minLength": 1, "maxLength": 1, "description": "empty-cell character, default '.'"},
                "coord_style": {"type": "string", "enum": ["A1", "rc", "index"],
                                "description": "how cells are named in the answer: 'A1' = column letter + row number (row 1 = top unless row_origin is 'bottom'), 'rc' = 'row,col' zero-based (default), 'index' = row*width+col"},
                "row_origin": {"type": "string", "enum": ["top", "bottom"], "description": "for A1 style: where row number 1 is, default top"}},
            "required": ["board", "k", "players"]},
    fn=board_lines, families=("think_ahead",), model_callable=True, max_ms=1500))

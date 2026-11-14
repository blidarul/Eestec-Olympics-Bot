"""Adapter: a prep-written simulator (/memory/<game>/simulator.py) -> the `game` interface of solvers/search.py
and solvers/mcts.py. No game-specific code (10.7).

Simulator contract (what prep/synthesis.py writes today, plus the one piece it lacks, see issue to bld):
    class State:                      # State() = initial state, any attributes
        legal_actions() -> [str]      # (also accepted: legal())
        step(action) -> State         # new state; may sample chance; None = mutated in place (also: apply())
        is_terminal() -> bool
        evaluate(seat) -> float       # (also: score(seat)) from `seat`'s point of view
        current                       # optional: seat to move (also: to_move())
        key()                         # optional: int hash, else a structural hash is built here
    parse(observation: str, seat: int) -> State     # module level (or State.from_observation): REQUIRED to verify

SimGame maps that to: parse(obs, seat) legal(s) apply(s, a) is_terminal(s) score(s, seat) [to_move(s)] [key(s)].
`key` uses Zobrist hashing (optimization.zobrist) for a flat `board` list, XORed with a structural hash of the
other attributes; plain python hashing when optimization/ is missing.
"""
import copy
import inspect
import random

_MASK = (1 << 64) - 1


def _freeze(v):
    if isinstance(v, (list, tuple)):
        return tuple(_freeze(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted(((str(k), _freeze(x)) for k, x in v.items())))
    if isinstance(v, (set, frozenset)):
        return frozenset(_freeze(x) for x in v)
    return v


def _attrs(state):
    d = getattr(state, "__dict__", None)
    if d is not None:
        return d
    return {n: getattr(state, n) for n in getattr(type(state), "__slots__", ())}


def _first(obj, names):
    for n in names:
        f = getattr(obj, n, None)
        if callable(f):
            return f
    return None


class SimGame:
    def __init__(self, state_cls, parse_fn=None):
        self.state_cls = state_cls
        self._parse = parse_fn
        init = state_cls()
        self._legal_name = next((n for n in ("legal_actions", "legal") if callable(getattr(init, n, None))), None)
        self._step_name = next((n for n in ("step", "apply") if callable(getattr(init, n, None))), None)
        self._score_name = next((n for n in ("evaluate", "score") if callable(getattr(init, n, None))), None)
        if not (self._legal_name and self._step_name and callable(getattr(init, "is_terminal", None))):
            raise TypeError("simulator State lacks legal_actions/step/is_terminal")
        self._turn_attr = next((n for n in ("current", "to_move", "player") if hasattr(init, n)), None)
        if self._turn_attr is not None:
            self.to_move = self._to_move          # only offered when the state tells whose turn it is
        if callable(getattr(init, "sample_hidden", None)):
            self.determinize = lambda s, rng: s.sample_hidden(rng)   # optional hidden-information sampler (M6)
        self._hasher = None
        self._inplace = self._detect_inplace(init)

    # --- construction ----------------------------------------------------------------------
    def _detect_inplace(self, init):
        try:
            acts = getattr(init, self._legal_name)()
            if not acts:
                return False
            before = repr(_freeze(_attrs(init)))
            r = getattr(init, self._step_name)(acts[0])
            return r is None or (r is init and repr(_freeze(_attrs(init))) != before)
        except Exception:
            return True

    # --- interface -------------------------------------------------------------------------
    def parse(self, obs, seat=0):
        fn = self._parse
        if fn is None:
            raise NotImplementedError("simulator has no parse(observation, seat)")
        try:
            n = len(inspect.signature(fn).parameters)
        except (TypeError, ValueError):
            n = 2
        return fn(obs, seat) if n >= 2 else fn(obs)

    @property
    def can_parse(self):
        return self._parse is not None

    def legal(self, s):
        return [str(a) for a in (getattr(s, self._legal_name)() or [])]

    def apply(self, s, a):
        if self._inplace:
            s = copy.deepcopy(s)
            r = getattr(s, self._step_name)(a)
            return s if r is None else r
        r = getattr(s, self._step_name)(a)
        return s if r is None else r

    def is_terminal(self, s):
        return bool(s.is_terminal())

    def score(self, s, seat):
        if self._score_name is None:
            return 0.0
        return float(getattr(s, self._score_name)(seat))

    def _to_move(self, s):
        v = getattr(s, self._turn_attr)
        return v() if callable(v) else v

    def key(self, s):
        k = getattr(s, "key", None)
        if callable(k):
            return int(k()) & _MASK
        attrs = _attrs(s)
        board = attrs.get("board")
        rest = {n: v for n, v in attrs.items() if n != "board"}
        h = hash(_freeze(rest)) & _MASK
        if isinstance(board, (list, tuple)) and all(c is None or (isinstance(c, int) and 0 <= c < 8) for c in board):
            try:
                if self._hasher is None or self._hasher.num_cells != len(board):
                    from optimization.zobrist import ZobristHasher
                    self._hasher = ZobristHasher(num_cells=len(board), num_pieces=8)
                return (self._hasher.hash_grid(list(board), 0) ^ h) & _MASK
            except Exception:
                pass
        return (hash(_freeze(board)) ^ h) & _MASK

    def initial(self):
        return self.state_cls()

    def has_chance(self, state=None, tries=6, rng=None):
        """True if applying the same move to the same state can give different states."""
        rng = rng or random.Random(1)
        s = state if state is not None else self.initial()
        for _ in range(8):
            if self.is_terminal(s):
                break
            ms = self.legal(s)
            if not ms:
                break
            m = rng.choice(ms)
            outs = {repr(_freeze(_attrs(self.apply(s, m)))) for _ in range(tries)}
            if len(outs) > 1:
                return True
            s = self.apply(s, m)
        return False


def load_simulator_source(src, name="simulator"):
    """Exec simulator source in a private namespace and wrap it. Raises on any problem."""
    ns = {"__name__": name}
    exec(compile(src, name, "exec"), ns)
    cls = ns.get("State")
    if cls is None:
        raise ValueError("simulator defines no State class")
    parse = ns.get("parse") or getattr(cls, "from_observation", None)
    return SimGame(cls, parse)


_CACHE = {}


def load_simulator(path):
    """Load /memory/<game>/simulator.py (cached by path + mtime + size). Raises on any problem."""
    import os
    st = os.stat(path)
    ck = (path, st.st_mtime_ns, st.st_size)
    g = _CACHE.get(ck)
    if g is None:
        with open(path, encoding="utf-8") as f:
            g = load_simulator_source(f.read(), name=os.path.basename(path))
        _CACHE.clear()
        _CACHE[ck] = g
    return g

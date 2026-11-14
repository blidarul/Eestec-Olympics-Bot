"""Static inventory: per module lines and public defs, with owner; writes out/inventory.md."""
import ast, os
OWN = {"core": "bld", "prep": "bld", "optimization": "bld", "main.py": "bld", "solvers": "alex", "chat": "mbappe", "opponent": "mbappe"}
def owner(p):
    if p.startswith("strategies"):
        s = p.replace("\\", "/").split("/")
        if len(s) > 2 and s[1] in ("think_ahead", "guessing"): return "alex"
        if len(s) > 2 and s[1] in ("bluff", "deals", "read_opponent", "truth", "guardrails"): return "mbappe"
        return "bld(shared)"
    return OWN.get(p.replace("\\", "/").split("/")[0], "?")
rows = []
for d in ["main.py", "core", "prep", "optimization", "solvers", "strategies", "chat", "opponent"]:
    files = [d] if d.endswith(".py") else [os.path.join(r, f) for r, _, fs in os.walk(d) if "__pycache__" not in r for f in fs if f.endswith(".py")]
    for f in sorted(files):
        src = open(f, encoding="utf8", errors="ignore").read()
        try: t = ast.parse(src)
        except Exception: continue
        defs = [n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
        rows.append((f.replace("\\", "/"), src.count("\n") + 1, owner(f), defs))
with open("tests/alex/audit/out/inventory.md", "w", encoding="utf8") as o:
    o.write("| module | lines | owner | public defs (n: first 6) |\n|---|---|---|---|\n")
    for f, n, ow, dfs in rows:
        if n < 3 and not dfs: continue
        o.write(f"| {f} | {n} | {ow} | {len(dfs)}: {', '.join(dfs[:6])} |\n")
print(len(rows), "modules", sum(r[1] for r in rows), "lines")

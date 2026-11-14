"""Run each test file with a timeout; print file, result, seconds (failures named)."""
import glob, subprocess, sys, time, concurrent.futures as cf
def one(f):
    t = time.time()
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", f, "-q", "--no-header", "-p", "no:cacheprovider", "-x"],
                           capture_output=True, text=True, timeout=240)
        last = (p.stdout.strip().splitlines() or ["?"])[-1][:90]
    except subprocess.TimeoutExpired: last = "TIMEOUT 240s"
    return f, last, round(time.time() - t)
fs = sorted(glob.glob("tests/bld/test_*.py") + glob.glob("tests/mbappe/test_*.py"))
with cf.ThreadPoolExecutor(3) as ex:
    for f, l, s in ex.map(one, fs): print(f"{f:44} {s:4}s  {l}")

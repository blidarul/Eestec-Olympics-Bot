"""Hardware Budget Enforcement & Garbage Collection Optimization.
Ensures containers stay strictly within 2 CPU / 2 GB RAM limits (Rules 5.12, 5.13).
Owned by agent `bld`.
"""
from __future__ import annotations

import contextlib
import gc
import os
import sys
from typing import Generator


def get_memory_rss_mb() -> float:
    """Return resident memory (RSS) in megabytes for the current process across Linux & Windows."""
    # 1. Linux /proc/self/statm (in tournament containers)
    if os.path.exists("/proc/self/statm"):
        try:
            with open("/proc/self/statm", "r") as fh:
                fields = fh.read().split()
                if len(fields) >= 2:
                    rss_pages = int(fields[1])
                    page_size_kb = os.sysconf("SC_PAGE_SIZE") / 1024.0 if hasattr(os, "sysconf") else 4.0
                    return (rss_pages * page_size_kb) / 1024.0
        except (OSError, ValueError):
            pass

    # 2. Windows K32GetProcessMemoryInfo via ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / (1024.0 * 1024.0)
        except Exception:
            pass

    return 0.0


def check_memory_budget(limit_mb: float = 1800.0) -> bool:
    """Check if resident memory is within safe operating limits (< 1.8 GB for 2 GB limit)."""
    rss = get_memory_rss_mb()
    if rss > limit_mb:
        print(f"[optimization/budget] WARNING: High RSS memory: {rss:.1f} MB (limit: {limit_mb} MB)", file=sys.stderr)
        return False
    return True


@contextlib.contextmanager
def pause_gc() -> Generator[None, None, None]:
    """Disable garbage collection during inner search loops to avoid latency spikes,
    then re-enable and optionally run an incremental collection.
    """
    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
            # Run generational collection after the turn finishes
            gc.collect(1)

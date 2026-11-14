"""Search Loop & Simulator Profiler.
Measures execution throughput (node expansions per second) and transition bottlenecks.
Owned by agent `bld`.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from .budget import get_memory_rss_mb


def time_execution(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Execute a function and return (result, elapsed_seconds)."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def benchmark_throughput(func: Callable[..., Any], iterations: int = 1000, *args: Any, **kwargs: Any) -> float:
    """Benchmark the throughput (calls per second) of a callable."""
    start = time.perf_counter()
    for _ in range(iterations):
        func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    if elapsed <= 0:
        return float("inf")
    return iterations / elapsed


def profile_memory_delta(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Profile RSS memory delta (in MB) during a function execution."""
    rss_before = get_memory_rss_mb()
    result = func(*args, **kwargs)
    rss_after = get_memory_rss_mb()
    return result, max(0.0, rss_after - rss_before)

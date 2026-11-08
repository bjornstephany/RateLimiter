import threading

import pytest

import rate_limiter
from rate_limiter import RateLimiter


class FakeClock:
    """Stand-in for the `time` module: only monotonic() is needed."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    # Replace the `time` name inside the rate_limiter module only, so the
    # rest of the process (pytest, threading, ...) keeps the real clock.
    monkeypatch.setattr(rate_limiter, "time", fake)
    return fake


# --------------------------------------------------------------------------
# Basic behaviour
# --------------------------------------------------------------------------

def test_allows_requests_up_to_limit(clock):
    rl = RateLimiter(limit=3, window_seconds=10)
    assert [rl.allow("a") for _ in range(3)] == [True, True, True]


def test_blocks_request_over_limit(clock):
    rl = RateLimiter(limit=3, window_seconds=10)
    for _ in range(3):
        rl.allow("a")
    assert rl.allow("a") is False
    assert rl.allow("a") is False  # stays blocked while time is frozen


def test_zero_limit_always_denies(clock):
    rl = RateLimiter(limit=0, window_seconds=10)
    assert rl.allow("a") is False
    clock.advance(1000)
    assert rl.allow("a") is False


def test_keys_are_independent(clock):
    rl = RateLimiter(limit=1, window_seconds=10)
    assert rl.allow("alice") is True
    assert rl.allow("alice") is False
    assert rl.allow("bob") is True  # bob unaffected by alice's usage
    assert rl.allow("bob") is False


# --------------------------------------------------------------------------
# Time-based behaviour (no real waiting)
# --------------------------------------------------------------------------

def test_allows_again_after_window_passes(clock):
    rl = RateLimiter(limit=2, window_seconds=60)
    assert rl.allow("a") and rl.allow("a")
    assert rl.allow("a") is False

    clock.advance(61)
    assert rl.allow("a") is True


def test_still_blocked_just_before_window_ends(clock):
    rl = RateLimiter(limit=1, window_seconds=10)
    assert rl.allow("a") is True

    clock.advance(9.999)
    assert rl.allow("a") is False


def test_request_expires_exactly_at_window_boundary(clock):
    # The code uses `<= window_start`, so a request made exactly
    # window_seconds ago is no longer counted.
    rl = RateLimiter(limit=1, window_seconds=10)
    assert rl.allow("a") is True

    clock.advance(10)
    assert rl.allow("a") is True


def test_window_is_sliding_not_fixed(clock):
    rl = RateLimiter(limit=2, window_seconds=10)

    assert rl.allow("a") is True        # t=0
    clock.advance(5)
    assert rl.allow("a") is True        # t=5
    assert rl.allow("a") is False       # t=5, full

    clock.advance(5)                    # t=10: first request expired
    assert rl.allow("a") is True        # slot freed, t=10 logged
    assert rl.allow("a") is False       # t=5 and t=10 still in window

    clock.advance(5)                    # t=15: t=5 request expired
    assert rl.allow("a") is True
    assert rl.allow("a") is False


def test_denied_requests_are_not_recorded(clock):
    # If rejected calls were logged, hammering the limiter would keep the
    # caller locked out forever.
    rl = RateLimiter(limit=1, window_seconds=10)
    assert rl.allow("a") is True        # t=0

    for _ in range(5):
        clock.advance(1)
        assert rl.allow("a") is False   # t=1..5, all rejected

    clock.advance(5)                    # t=10: only the t=0 request mattered
    assert rl.allow("a") is True


def test_fractional_window(clock):
    rl = RateLimiter(limit=1, window_seconds=0.5)
    assert rl.allow("a") is True
    clock.advance(0.25)
    assert rl.allow("a") is False
    clock.advance(0.25)
    assert rl.allow("a") is True


def test_partial_expiry_frees_only_expired_slots(clock):
    rl = RateLimiter(limit=3, window_seconds=10)
    rl.allow("a")                       # t=0
    clock.advance(4)
    rl.allow("a")                       # t=4
    rl.allow("a")                       # t=4
    assert rl.allow("a") is False

    clock.advance(6)                    # t=10: only the t=0 request expired
    assert rl.allow("a") is True        # one slot freed
    assert rl.allow("a") is False       # but only one


def test_expired_entries_are_pruned_from_memory(clock):
    rl = RateLimiter(limit=100, window_seconds=10)
    for _ in range(50):
        rl.allow("a")
    assert len(rl.requests["a"]) == 50

    clock.advance(11)
    rl.allow("a")
    assert len(rl.requests["a"]) == 1   # old 50 dropped, new one added


def test_only_the_calling_keys_log_is_pruned(clock):
    rl = RateLimiter(limit=5, window_seconds=10)
    rl.allow("a")
    rl.allow("b")
    clock.advance(11)

    rl.allow("a")  # prunes only "a"
    assert len(rl.requests["a"]) == 1
    assert len(rl.requests["b"]) == 1   # stale until "b" is next used


def test_many_cycles_of_fill_and_expire(clock):
    rl = RateLimiter(limit=5, window_seconds=60)
    for _ in range(100):  # 100 minutes of simulated time, instant in reality
        assert all(rl.allow("a") for _ in range(5))
        assert rl.allow("a") is False
        clock.advance(60)


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------

def test_thread_safety_never_exceeds_limit(clock):
    limit, n_threads = 10, 100
    rl = RateLimiter(limit=limit, window_seconds=60)
    barrier = threading.Barrier(n_threads)
    results = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()  # release all threads at once to maximise contention
        allowed = rl.allow("shared")
        with results_lock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == n_threads
    assert sum(results) == limit


def test_thread_safety_across_multiple_keys(clock):
    limit, n_keys, per_key_threads = 5, 4, 20
    rl = RateLimiter(limit=limit, window_seconds=60)
    barrier = threading.Barrier(n_keys * per_key_threads)
    allowed_by_key = {f"k{i}": 0 for i in range(n_keys)}
    results_lock = threading.Lock()

    def worker(key):
        barrier.wait()
        if rl.allow(key):
            with results_lock:
                allowed_by_key[key] += 1

    threads = [
        threading.Thread(target=worker, args=(f"k{i}",))
        for i in range(n_keys)
        for _ in range(per_key_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert allowed_by_key == {f"k{i}": limit for i in range(n_keys)}


# --------------------------------------------------------------------------
# One sanity check against the real clock (fast, no sleeping)
# --------------------------------------------------------------------------

def test_works_with_real_clock_without_sleeping():
    rl = RateLimiter(limit=2, window_seconds=3600)
    assert rl.allow("a") is True
    assert rl.allow("a") is True
    assert rl.allow("a") is False
# Rate Limiter
A thread-safe, per-key rate limiter for protecting calls to broker and data-provider APIs.

# Motivation
Brokers and data providers have a cap on how often we can call their APIs, e.g. 200 requests a minute. If we go over, requests failing. Build a rate limiter our code would call before making a request.

# Algorithm: Sliding window log
Pros: High precesion. High speed. \
Cons: High memory usage (one timestamp per accepted request, up to `limit` per key).

# Testing
Time is controlled by patching time.monotonic (or injecting a fake clock), so a "60 second" window can be tested instantly by advancing a fake clock. Cases covered:
    Requests up to the limit are allowed; the next one is rejected.
    Requests are allowed again once the window has passed (fake clock advanced).
    Keys are isolated from each other.
    Rejected requests don't consume quota.
    Concurrent calls from many threads never accept more than limit.

Run with: `pytest`



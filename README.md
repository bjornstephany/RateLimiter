Brokers and data providers have a cap on how often we can call their APIs, e.g. 200 requests a minute. If we go over, requests failing. Build a rate limiter our code would call before making a request.

1.⁠ ⁠RateLimiter(limit, window_seconds) with allow(key) -> bool. It returns True if a request for that key (for example a pod's name) can go through now, and False if it would go over limit requests in window_seconds.
2.⁠ ⁠Each key has its own limit, so one pod can't use up another's.
3.⁠ ⁠Pick an algorithm and be ready to say why you chose it over the others.
4.⁠ ⁠It must be safe to call from several threads at once.
5.⁠ ⁠Write tests, including ones that don't actually wait for time to pass.
6.⁠ ⁠Add a short README: what you chose, pros cons, and think a little bit of edge cases that would change the implementation like simultaneous users using the function at once etc, dont have to over engineer just describe some scenarios you can think of.
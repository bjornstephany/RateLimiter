import time
from collections import defaultdict, deque
import threading

class RateLimiter:
    
    def __init__(self, limit: int, window_seconds):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)
        self.lock = threading.Lock()
    
    def allow(self, key: str) -> bool:
        with self.lock:
            now = time.time()
            window_start = now - self.window_seconds
            request_log = self.requests[key]
            
            while request_log and request_log[0] <= window_start:
                request_log.popleft()
            
            if len(request_log) >= self.limit:
                return False
            
            request_log.append(now)
            return True
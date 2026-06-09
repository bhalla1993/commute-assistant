import time
import threading
from fastapi import HTTPException

class InMemoryRateLimiter:
    def __init__(self, max_calls: int, window_sec: int):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, key: str):
        now = int(time.time())
        with self._lock:
            bucket = self._buckets.setdefault(key, [])
            # Remove old timestamps
            bucket[:] = [t for t in bucket if now - t < self.window_sec]
            if len(bucket) >= self.max_calls:
                raise HTTPException(status_code=429, detail="Too many requests, slow down.")
            bucket.append(now)

    def reset(self):
        with self._lock:
            self._buckets.clear()

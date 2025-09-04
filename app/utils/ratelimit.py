import time
from typing import Dict

class SimpleRateLimiter:
    def __init__(self, capacity: int, window_seconds: int = 60):
        self.capacity = capacity
        self.window = window_seconds
        self.tokens: Dict[str, Dict[str, float]] = {}

    def allow(self, key: str) -> tuple[bool, int, float]:
        now = time.time()
        bucket = self.tokens.get(key, {"reset": now + self.window, "remaining": self.capacity})
        if now > bucket["reset"]:
            bucket = {"reset": now + self.window, "remaining": self.capacity}
        allowed = bucket["remaining"] > 0
        if allowed:
            bucket["remaining"] -= 1
        self.tokens[key] = bucket
        return allowed, bucket["remaining"], bucket["reset"]

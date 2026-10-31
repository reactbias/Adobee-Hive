"""Request guards for the public demo: shared-secret headers and rate limits on paid Claude calls.

The Hive's read and booking APIs are public by design (agents need them). What is guarded is what costs money
(Claude runs) or changes a business without its owner (card edits, reset).
"""

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config


def require_secret(request: Request, header: str, expected: str) -> None:
    """Reject the request unless `header` matches `expected`. An empty `expected` means the check is off."""
    if expected and not hmac.compare_digest(request.headers.get(header, ""), expected):
        raise HTTPException(403, f"Missing or wrong {header}.")


class RateLimiter:
    """Sliding-window limit per client plus one global cap, kept in memory (one backend instance)."""

    def __init__(self, per_client: int, total: int, window_s: int = 3600) -> None:
        self.per_client, self.total, self.window = per_client, total, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, request: Request) -> None:
        """Count one call for this client, or raise 429 when the client or the whole backend is over its limit."""
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        with self.lock:
            for key in (client, "*"):
                hits = self.hits[key]
                while hits and now - hits[0] > self.window:
                    hits.popleft()
            if len(self.hits[client]) >= self.per_client or len(self.hits["*"]) >= self.total:
                raise HTTPException(429, "Too many requests. Try again later.")
            self.hits[client].append(now)
            self.hits["*"].append(now)


# One budget for everything that may call Claude: agent runs and owner edit proposals.
llm_calls = RateLimiter(per_client=config.LLM_CALLS_PER_CLIENT_HOUR, total=config.LLM_CALLS_TOTAL_HOUR)
# Simulated traffic writes demand events; keep it to demo use.
simulations = RateLimiter(per_client=20, total=200)

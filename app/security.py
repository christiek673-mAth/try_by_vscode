"""Security middleware for IP whitelisting and rate limiting."""
import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce IP whitelist."""

    def __init__(self, app, whitelist: List[str]):
        super().__init__(app)
        self.whitelist = set(whitelist) if whitelist else None

    async def dispatch(self, request: Request, call_next):
        if self.whitelist:
            client_ip = request.client.host if request.client else None
            if client_ip not in self.whitelist:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied from IP: {client_ip}",
                )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter."""

    def __init__(self, app, requests_per_minute: int):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean old entries
        cutoff = now - 60
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > cutoff]
        
        # Check limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )
        
        self.requests[client_ip].append(now)
        return await call_next(request)

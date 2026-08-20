"""JWT Token blacklist for revocation support."""
import time
from typing import Optional, Set

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class TokenBlacklist:
    """Manage revoked JWT tokens."""
    
    def __init__(self, redis_url: Optional[str] = None, cleanup_interval: int = 3600):
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        
        # Try Redis first
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.redis.ping()
                self.backend = "redis"
            except Exception:
                self.redis = None
                self.backend = "memory"
                self._memory_blacklist: Set[str] = set()
                self._memory_expiry: dict = {}
        else:
            self.redis = None
            self.backend = "memory"
            self._memory_blacklist: Set[str] = set()
            self._memory_expiry: dict = {}
    
    def revoke(self, token_jti: str, expires_at: int):
        """
        Add token to blacklist.
        
        Args:
            token_jti: JWT ID (jti claim)
            expires_at: Token expiration timestamp
        """
        if self.backend == "redis":
            try:
                ttl = max(expires_at - int(time.time()), 1)
                self.redis.setex(f"blacklist:{token_jti}", ttl, "1")
            except Exception:
                pass
        else:
            self._memory_blacklist.add(token_jti)
            self._memory_expiry[token_jti] = expires_at
            self._cleanup_if_needed()
    
    def is_revoked(self, token_jti: str) -> bool:
        """Check if token is revoked."""
        if self.backend == "redis":
            try:
                return self.redis.exists(f"blacklist:{token_jti}") > 0
            except Exception:
                return False
        else:
            self._cleanup_if_needed()
            return token_jti in self._memory_blacklist
    
    def revoke_user_tokens(self, user_id: str, expires_after: int = 86400):
        """
        Revoke all tokens for a user (requires pattern matching).
        This is a marker - actual tokens still need individual JTI revocation.
        """
        if self.backend == "redis":
            try:
                self.redis.setex(f"user_revoked:{user_id}", expires_after, str(int(time.time())))
            except Exception:
                pass
    
    def is_user_revoked(self, user_id: str, token_issued_at: int) -> bool:
        """Check if user's tokens issued before a certain time are revoked."""
        if self.backend == "redis":
            try:
                revoked_at = self.redis.get(f"user_revoked:{user_id}")
                if revoked_at:
                    return token_issued_at < int(revoked_at)
            except Exception:
                pass
        return False
    
    def _cleanup_if_needed(self):
        """Clean up expired tokens from memory backend."""
        if self.backend == "memory":
            now = time.time()
            if now - self._last_cleanup > self.cleanup_interval:
                expired = [jti for jti, exp in self._memory_expiry.items() if exp < now]
                for jti in expired:
                    self._memory_blacklist.discard(jti)
                    del self._memory_expiry[jti]
                self._last_cleanup = now
    
    def stats(self) -> dict:
        """Get blacklist statistics."""
        if self.backend == "redis":
            try:
                count = len(list(self.redis.scan_iter(match="blacklist:*")))
                return {"backend": "redis", "revoked_tokens": count}
            except Exception:
                return {"backend": "redis", "error": "unavailable"}
        else:
            return {
                "backend": "memory",
                "revoked_tokens": len(self._memory_blacklist),
            }

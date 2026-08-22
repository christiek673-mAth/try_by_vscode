"""Tests for query cache."""
import time

from app.cache import QueryCache


def test_memory_cache():
    cache = QueryCache(redis_url=None)
    assert cache.backend == "memory"
    
    # Test set and get
    cache.set("question1", "tenant1", "ds1", {"result": "data"})
    result = cache.get("question1", "tenant1", "ds1")
    assert result == {"result": "data"}
    
    # Test miss
    assert cache.get("nonexistent", "tenant1", "ds1") is None


def test_cache_ttl():
    cache = QueryCache(redis_url=None, default_ttl=1)
    cache.set("question1", "tenant1", "ds1", {"result": "data"}, ttl=1)
    
    # Should exist immediately
    assert cache.get("question1", "tenant1", "ds1") is not None
    
    # Should expire after 1 second
    time.sleep(1.1)
    assert cache.get("question1", "tenant1", "ds1") is None


def test_cache_invalidation():
    cache = QueryCache(redis_url=None)
    cache.set("question1", "tenant1", "ds1", {"result": "data"})
    
    # Should exist
    assert cache.get("question1", "tenant1", "ds1") is not None
    
    # Invalidate
    cache.invalidate("question1", "tenant1", "ds1")
    
    # Should not exist
    assert cache.get("question1", "tenant1", "ds1") is None


def test_cache_stats():
    cache = QueryCache(redis_url=None)
    stats = cache.stats()
    assert stats["backend"] == "memory"
    assert "keys" in stats

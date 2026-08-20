"""Tests for query history."""
import time

from app.query_history import QueryHistory


def test_add_and_retrieve(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history = QueryHistory(str(history_file))
    
    query_id = history.add(
        user_id="user1",
        tenant_id="tenant1",
        question="test question",
        sql="SELECT * FROM test",
        datasource="primary",
        row_count=10,
        execution_ms=100.5,
        success=True,
    )
    
    assert query_id is not None
    
    # Retrieve by ID
    entry = history.get_by_id(query_id)
    assert entry is not None
    assert entry.user_id == "user1"
    assert entry.question == "test question"


def test_user_history(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history = QueryHistory(str(history_file))
    
    # Add multiple queries
    for i in range(5):
        history.add(
            user_id="user1",
            tenant_id="tenant1",
            question=f"question {i}",
            sql=f"SELECT {i}",
            datasource="primary",
            row_count=i,
            execution_ms=100.0,
            success=True,
        )
    
    # Retrieve history
    entries = history.get_user_history("user1", "tenant1", limit=3)
    assert len(entries) == 3
    assert entries[0].question == "question 4"  # Most recent first


def test_search_history(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history = QueryHistory(str(history_file))
    
    history.add(
        user_id="user1",
        tenant_id="tenant1",
        question="查询订单",
        sql="SELECT * FROM orders",
        datasource="primary",
        row_count=10,
        execution_ms=100.0,
        success=True,
    )
    
    history.add(
        user_id="user1",
        tenant_id="tenant1",
        question="查询客户",
        sql="SELECT * FROM customers",
        datasource="primary",
        row_count=5,
        execution_ms=50.0,
        success=True,
    )
    
    # Search by keyword
    results = history.search("user1", "tenant1", "订单")
    assert len(results) == 1
    assert "订单" in results[0].question


def test_failed_query(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history = QueryHistory(str(history_file))
    
    query_id = history.add(
        user_id="user1",
        tenant_id="tenant1",
        question="bad question",
        sql="",
        datasource="primary",
        row_count=0,
        execution_ms=10.0,
        success=False,
        error="SQL syntax error",
    )
    
    entry = history.get_by_id(query_id)
    assert not entry.success
    assert entry.error == "SQL syntax error"


def test_stats(tmp_path):
    history_file = tmp_path / "history.jsonl"
    history = QueryHistory(str(history_file))
    
    history.add("user1", "tenant1", "q1", "sql1", "ds1", 10, 100.0, True)
    history.add("user1", "tenant1", "q2", "sql2", "ds1", 0, 50.0, False, "error")
    
    stats = history.stats()
    assert stats["total_queries"] == 2
    assert stats["success_queries"] == 1
    assert stats["success_rate"] == 50.0

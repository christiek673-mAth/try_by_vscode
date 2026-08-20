from sqlalchemy import create_engine, text

from app.catalog import Catalog
from app.policy import SQLPolicy, SQLPolicyError


def build_policy():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (id INTEGER, amount REAL, tenant_id TEXT)"))
    catalog = Catalog(engine)
    return SQLPolicy(catalog, "sqlite", 10, ["email"])


def test_policy_adds_limit_and_tenant_filter():
    sql = build_policy().validate_and_rewrite("SELECT id, amount FROM orders", "tenant-a")
    assert "LIMIT 10" in sql.upper()
    assert "tenant_id" in sql
    assert "tenant-a" in sql


def test_policy_rejects_write_query():
    try:
        build_policy().validate_and_rewrite("DELETE FROM orders", "tenant-a")
    except SQLPolicyError as exc:
        assert "SELECT" in str(exc)
    else:
        raise AssertionError("write query was accepted")


def test_policy_rejects_unknown_table():
    try:
        build_policy().validate_and_rewrite("SELECT * FROM secrets", "tenant-a")
    except SQLPolicyError as exc:
        assert "denied" in str(exc)
    else:
        raise AssertionError("unknown table was accepted")


def test_policy_scopes_joined_tables():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (id INTEGER, customer_id INTEGER, tenant_id TEXT)"))
        connection.execute(text("CREATE TABLE customers (id INTEGER, name TEXT, tenant_id TEXT)"))
    policy = SQLPolicy(Catalog(engine), "sqlite", 10, [])

    sql = policy.validate_and_rewrite(
        "SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id",
        "tenant-a",
    )

    assert "o.tenant_id = 'tenant-a'" in sql
    assert "c.tenant_id = 'tenant-a'" in sql


def test_policy_scopes_cte_without_scoping_cte_alias_again():
    sql = build_policy().validate_and_rewrite(
        "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent",
        "tenant-a",
    )

    assert sql.upper().count("TENANT_ID") == 1
    assert "orders.tenant_id = 'tenant-a'" in sql


def test_policy_does_not_duplicate_existing_tenant_filter():
    sql = build_policy().validate_and_rewrite(
        "SELECT id FROM orders WHERE tenant_id = 'tenant-a'",
        "tenant-a",
    )

    assert sql.upper().count("TENANT_ID") == 1


def test_unqualified_join_filter_does_not_disable_other_table_scope():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (id INTEGER, customer_id INTEGER, tenant_id TEXT)"))
        connection.execute(text("CREATE TABLE customers (id INTEGER, tenant_id TEXT)"))
    policy = SQLPolicy(Catalog(engine), "sqlite", 10, [])

    sql = policy.validate_and_rewrite(
        "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id "
        "WHERE tenant_id = 'tenant-a'",
        "tenant-a",
    )

    assert "o.tenant_id = 'tenant-a'" in sql
    assert "c.tenant_id = 'tenant-a'" in sql


def test_policy_rejects_multiple_statements_and_bind_limit():
    policy = build_policy()
    for query, expected in [
        ("SELECT id FROM orders; SELECT id FROM orders", "one SQL statement"),
        ("SELECT id FROM orders LIMIT ?", "positive integer"),
    ]:
        try:
            policy.validate_and_rewrite(query, "tenant-a")
        except SQLPolicyError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("unsafe query was accepted")


def test_request_limit_cannot_bypass_service_limit():
    sql = build_policy().validate_and_rewrite("SELECT id FROM orders", "tenant-a", 5000)
    assert "LIMIT 10" in sql.upper()


def test_zero_request_limit_is_rejected():
    try:
        build_policy().validate_and_rewrite("SELECT id FROM orders", "tenant-a", 0)
    except SQLPolicyError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("zero row limit was accepted")
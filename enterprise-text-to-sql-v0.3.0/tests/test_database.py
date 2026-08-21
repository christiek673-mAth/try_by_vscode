from sqlalchemy import create_engine, text

from app.database import execute_query


def test_sensitive_alias_is_masked():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE customers (email TEXT, tenant_id TEXT)"))
        connection.execute(text("INSERT INTO customers VALUES ('alice@example.com', 'demo')"))

    rows = execute_query(
        engine,
        "SELECT email AS customer_email FROM customers",
        ["email"],
    )

    assert rows == [{"customer_email": "***MASKED***"}]
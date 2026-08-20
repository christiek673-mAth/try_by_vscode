import os
from typing import Dict, List, Set

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import sqlglot
from sqlglot import exp


def create_engine_for_url(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def initialize_demo_database(engine: Engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        return
    os.makedirs("data", exist_ok=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS customers ("
                "id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, tenant_id TEXT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS orders ("
                "id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT NOT NULL, "
                "product TEXT NOT NULL, amount REAL NOT NULL, tenant_id TEXT NOT NULL)"
            )
        )
        count = connection.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        if count == 0:
            connection.execute(
                text(
                    "INSERT INTO customers (id, name, email, tenant_id) VALUES "
                    "(1, 'Alice', 'alice@example.com', 'demo'), "
                    "(2, 'Bob', 'bob@example.com', 'demo'), "
                    "(3, 'Carol', 'carol@example.com', 'other')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO orders (customer_id, order_date, product, amount, tenant_id) VALUES "
                    "(1, '2026-08-01', 'Notebook', 32.50, 'demo'), "
                    "(2, '2026-08-03', 'Keyboard', 89.00, 'demo'), "
                    "(3, '2026-08-04', 'Monitor', 220.00, 'other')"
                )
            )


def execute_query(engine: Engine, sql: str, sensitive_columns: List[str], dialect: str = "sqlite") -> List[Dict]:
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        rows = [dict(row) for row in result.mappings().all()]
    sensitive = _sensitive_result_columns(sql, sensitive_columns, dialect)
    for row in rows:
        for key in list(row.keys()):
            if key.lower() in sensitive and row[key] is not None:
                row[key] = "***MASKED***"
    return rows


def _sensitive_result_columns(sql: str, sensitive_columns: List[str], dialect: str) -> Set[str]:
    sensitive = {column.lower() for column in sensitive_columns}
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return sensitive
    output_columns = set(sensitive)
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if not select:
        return output_columns
    for projection in select.expressions:
        source_columns = [column for column in projection.find_all(exp.Column)]
        if any(column.name.lower() in sensitive for column in source_columns):
            output_columns.add(projection.alias_or_name.lower())
    return output_columns
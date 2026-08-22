from typing import List, Set

import sqlglot
from sqlglot import exp

from app.catalog import Catalog


class SQLPolicyError(ValueError):
    pass


class SQLPolicy:
    def __init__(self, catalog: Catalog, dialect: str, max_rows: int, sensitive_columns: List[str]):
        self.catalog = catalog
        self.dialect = dialect
        self.max_rows = max_rows
        self.sensitive_columns = set(column.lower() for column in sensitive_columns)

    def validate_and_rewrite(self, sql: str, tenant_id: str, max_rows: int = None) -> str:
        candidate = sql.strip()
        if not candidate:
            raise SQLPolicyError("SQL is empty")
        if "--" in candidate or "/*" in candidate:
            raise SQLPolicyError("SQL comments are not allowed")
        try:
            statements = sqlglot.parse(candidate, read=self.dialect)
        except Exception as exc:
            raise SQLPolicyError("SQL parsing failed: {}".format(exc))
        if len(statements) != 1:
            raise SQLPolicyError("Only one SQL statement is allowed")
        tree = statements[0]
        if not isinstance(tree, (exp.Select, exp.With)):
            raise SQLPolicyError("Only SELECT queries are allowed")

        allowed = set(self.catalog.tables.keys())
        referenced = self._referenced_tables(tree)
        unknown = referenced - allowed
        if unknown:
            raise SQLPolicyError("Table access denied: {}".format(", ".join(sorted(unknown))))
        if not referenced:
            raise SQLPolicyError("Query must reference an approved table")

        tree = self._apply_tenant_filter(tree, tenant_id)
        limit = self.max_rows if max_rows is None else min(max_rows, self.max_rows)
        if limit <= 0:
            raise SQLPolicyError("Row limit must be positive")
        if not tree.args.get("limit"):
            tree = tree.limit(limit)
        else:
            limit_expression = tree.args["limit"].expression
            if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
                raise SQLPolicyError("LIMIT must be a positive integer")
            if int(limit_expression.name) > limit:
                tree = tree.limit(limit)
        return tree.sql(dialect=self.dialect)

    def _referenced_tables(self, tree) -> Set[str]:
        ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        return {
            table.name.lower()
            for table in tree.find_all(exp.Table)
            if table.name.lower() not in ctes
        }

    def _apply_tenant_filter(self, tree, tenant_id: str):
        # Apply the predicate to every SELECT that reads a tenant-scoped physical
        # table. This keeps CTEs and nested subqueries isolated independently.
        for select in tree.find_all(exp.Select):
            aliases = self._local_tenant_tables(select)
            for alias in aliases:
                predicate = exp.EQ(
                    this=exp.column("tenant_id", table=alias),
                    expression=exp.Literal.string(tenant_id),
                )
                if not self._contains_predicate(select, alias, tenant_id, len(aliases)):
                    where = select.args.get("where")
                    if where:
                        predicate = exp.and_(where.this, predicate)
                    select.set("where", exp.Where(this=predicate))
        return tree

    def _local_tenant_tables(self, select) -> List[str]:
        sources = []
        from_clause = select.args.get("from") or select.args.get("from_")
        if from_clause and isinstance(from_clause.this, exp.Table):
            sources.append(from_clause.this)
        for join in select.args.get("joins") or []:
            if isinstance(join.this, exp.Table):
                sources.append(join.this)
        return [
            table.alias_or_name
            for table in sources
            if table.name.lower() in self.catalog.tables
            and self.catalog.has_column(table.name, "tenant_id")
        ]

    @staticmethod
    def _contains_predicate(select, alias: str, tenant_id: str, alias_count: int) -> bool:
        for equality in select.find_all(exp.EQ):
            column = equality.args.get("this")
            value = equality.args.get("expression")
            if not isinstance(column, exp.Column) or column.name.lower() != "tenant_id":
                continue
            if column.table and column.table.lower() != alias.lower():
                continue
            if not column.table and alias_count != 1:
                continue
            if isinstance(value, exp.Literal) and value.is_string and value.this == tenant_id:
                return True
        return False
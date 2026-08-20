import re
from typing import Dict, List

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.models import SourceTable


class Catalog:
    """Database schema catalog with a small lexical retriever.

    The interface is intentionally independent from the retriever implementation so
    it can later be backed by BM25 or an embedding index without changing the API.
    """

    def __init__(self, engine: Engine, allowed_tables: List[str] = None):
        self.engine = engine
        self.allowed_tables = set(item.lower() for item in (allowed_tables or []))
        self.tables: Dict[str, SourceTable] = {}
        self.refresh()

    def refresh(self) -> None:
        inspector = inspect(self.engine)
        self.tables = {}
        for name in inspector.get_table_names():
            if self.allowed_tables and name.lower() not in self.allowed_tables:
                continue
            columns = []
            for column in inspector.get_columns(name):
                columns.append(
                    {
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": bool(column.get("nullable", True)),
                    }
                )
            self.tables[name.lower()] = SourceTable(
                name=name,
                description="",
                columns=columns,
            )

    def all(self) -> List[SourceTable]:
        return list(self.tables.values())

    def public(self, hidden_columns: List[str] = None) -> List[SourceTable]:
        hidden = set(column.lower() for column in (hidden_columns or []))
        return [
            table.copy(
                update={
                    "columns": [
                        column
                        for column in table.columns
                        if column["name"].lower() not in hidden
                    ]
                }
            )
            for table in self.tables.values()
        ]

    def search(self, question: str, top_k: int) -> List[SourceTable]:
        terms = set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", question.lower()))
        scored = []
        for table in self.tables.values():
            haystack = " ".join(
                [table.name.lower()] + [column["name"].lower() for column in table.columns]
            )
            score = sum(1 for term in terms if term in haystack)
            scored.append((score, table.name, table))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [table.copy(update={"score": float(score)}) for score, _, table in scored[:top_k]]

    @staticmethod
    def prompt_context(tables: List[SourceTable], hidden_columns: List[str] = None) -> str:
        hidden = set(column.lower() for column in (hidden_columns or []))
        chunks = []
        for table in tables:
            columns = ", ".join(
                "{name} ({type})".format(name=column["name"], type=column["type"])
                for column in table.columns
                if column["name"].lower() not in hidden
            )
            chunks.append("TABLE {name}: {columns}".format(name=table.name, columns=columns))
        return "\n".join(chunks)

    def has_column(self, table_name: str, column_name: str) -> bool:
        table = self.tables.get(table_name.lower())
        return bool(table and any(item["name"].lower() == column_name.lower() for item in table.columns))
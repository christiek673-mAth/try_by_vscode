import time
import uuid

from app.audit import AuditLogger
from app.catalog import Catalog
from app.database import execute_query
from app.llm import TextToSQLModel
from app.models import QueryRequest, QueryResponse
from app.policy import SQLPolicy


class QueryService:
    def __init__(
        self,
        engine,
        catalog: Catalog,
        model: TextToSQLModel,
        policy: SQLPolicy,
        audit: AuditLogger,
        catalog_top_k: int = 8,
    ):
        self.engine = engine
        self.catalog = catalog
        self.model = model
        self.policy = policy
        self.audit = audit
        self.catalog_top_k = catalog_top_k

    def answer(self, request: QueryRequest) -> QueryResponse:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        sources = self.catalog.search(request.question, self.catalog_top_k)
        try:
            raw_sql, explanation = self.model.generate(
                request.question,
                self.catalog.prompt_context(sources, list(self.policy.sensitive_columns)),
                request.tenant_id,
            )
            sql = self.policy.validate_and_rewrite(raw_sql, request.tenant_id, request.max_rows)
            rows = (
                execute_query(
                    self.engine,
                    sql,
                    list(self.policy.sensitive_columns),
                    self.policy.dialect,
                )
                if request.execute
                else []
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            self.audit.write(
                {
                    "event": "query_succeeded",
                    "request_id": request_id,
                    "user_id": request.user_id,
                    "tenant_id": request.tenant_id,
                    "question": request.question,
                    "sql": sql,
                    "row_count": len(rows),
                    "execution_ms": elapsed,
                }
            )
            return QueryResponse(
                request_id=request_id,
                question=request.question,
                sql=sql,
                explanation=explanation,
                sources=sources,
                rows=rows,
                row_count=len(rows),
                execution_ms=elapsed if request.execute else None,
                model=self.model.name,
                warnings=["Sensitive columns are masked in returned rows."] if self.policy.sensitive_columns else [],
            )
        except Exception as exc:
            self.audit.write(
                {
                    "event": "query_failed",
                    "request_id": request_id,
                    "user_id": request.user_id,
                    "tenant_id": request.tenant_id,
                    "question": request.question,
                    "error": str(exc),
                }
            )
            raise
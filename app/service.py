import time
import uuid

from app.audit import AuditLogger
from app.auth import UserContext
from app.catalog import Catalog
from app.database import execute_query
from app.datasource import DataSourceRegistry
from app.llm import TextToSQLModel
from app.models import QueryRequest, QueryResponse
from app.permissions import PermissionEngine
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
        datasource_registry: DataSourceRegistry = None,
        permission_engine: PermissionEngine = None,
        query_cache=None,
        query_history=None,
        prompt_guard=None,
    ):
        self.engine = engine
        self.catalog = catalog
        self.model = model
        self.policy = policy
        self.audit = audit
        self.catalog_top_k = catalog_top_k
        self.datasource_registry = datasource_registry
        self.permission_engine = permission_engine
        self.query_cache = query_cache
        self.query_history = query_history
        self.prompt_guard = prompt_guard

    def answer(self, request: QueryRequest, user_context: UserContext = None) -> QueryResponse:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        
        # Prompt injection detection
        if self.prompt_guard:
            is_safe, warnings = self.prompt_guard.validate(request.question)
            if not is_safe:
                pass  # Will raise PromptInjectionError if strict_mode enabled
        
        # Check cache first
        if self.query_cache and request.execute:
            cached = self.query_cache.get(
                request.question,
                request.tenant_id,
                request.datasource,
                request.user_id,
            )
            if cached:
                cached["request_id"] = request_id
                cached["from_cache"] = True
                return QueryResponse(**cached)
        
        # Select datasource
        if self.datasource_registry:
            try:
                engine = self.datasource_registry.get_engine(request.datasource)
            except ValueError:
                engine = self.engine
        else:
            engine = self.engine
        
        sources = self.catalog.search(request.question, self.catalog_top_k)
        
        # Filter sources by user permissions
        if self.permission_engine and user_context:
            filtered_sources = []
            for source in sources:
                if self.permission_engine.check_table_access(
                    user_context, request.datasource, source.name
                ):
                    filtered_sources.append(source)
            sources = filtered_sources
        
        try:
            raw_sql, explanation = self.model.generate(
                request.question,
                self.catalog.prompt_context(sources, list(self.policy.sensitive_columns)),
                request.tenant_id,
            )
            sql = self.policy.validate_and_rewrite(raw_sql, request.tenant_id, request.max_rows)
            rows = (
                execute_query(
                    engine,
                    sql,
                    list(self.policy.sensitive_columns),
                    self.policy.dialect,
                )
                if request.execute
                else []
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            
            # Build response
            response = QueryResponse(
                request_id=request_id,
                question=request.question,
                sql=sql,
                explanation=explanation,
                sources=sources,
                rows=rows,
                row_count=len(rows),
                execution_ms=elapsed if request.execute else None,
                model=self.model.name,
                datasource=request.datasource,
                warnings=["Sensitive columns are masked in returned rows."] if self.policy.sensitive_columns else [],
            )
            
            # Cache result
            if self.query_cache and request.execute:
                self.query_cache.set(
                    request.question,
                    request.tenant_id,
                    request.datasource,
                    response.dict(exclude={"request_id"}),
                    user_id=request.user_id,
                )
            
            # Add to history
            if self.query_history and request.execute:
                self.query_history.add(
                    user_id=request.user_id,
                    tenant_id=request.tenant_id,
                    question=request.question,
                    sql=sql,
                    datasource=request.datasource,
                    row_count=len(rows),
                    execution_ms=elapsed,
                    success=True,
                )
            
            # Enhanced audit with user context
            audit_data = {
                "event": "query_succeeded",
                "request_id": request_id,
                "user_id": request.user_id,
                "tenant_id": request.tenant_id,
                "question": request.question,
                "sql": sql,
                "row_count": len(rows),
                "execution_ms": elapsed,
                "datasource": request.datasource,
            }
            if user_context:
                audit_data["user_context"] = user_context.dict()
            
            self.audit.write(audit_data)
            
            return response
        except Exception as exc:
            # Add to history as failed
            if self.query_history:
                self.query_history.add(
                    user_id=request.user_id,
                    tenant_id=request.tenant_id,
                    question=request.question,
                    sql="",
                    datasource=request.datasource,
                    row_count=0,
                    execution_ms=round((time.perf_counter() - started) * 1000, 2),
                    success=False,
                    error=str(exc),
                )
            
            audit_data = {
                "event": "query_failed",
                "request_id": request_id,
                "user_id": request.user_id,
                "tenant_id": request.tenant_id,
                "question": request.question,
                "error": str(exc),
                "datasource": request.datasource,
            }
            if user_context:
                audit_data["user_context"] = user_context.dict()
            
            self.audit.write(audit_data)
            raise


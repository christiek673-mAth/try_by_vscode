from typing import List

from fastapi import FastAPI, HTTPException

from app.audit import AuditLogger
from app.catalog import Catalog
from app.config import settings
from app.database import create_engine_for_url, initialize_demo_database
from app.llm import LLMError, build_model
from app.models import QueryRequest, QueryResponse, SourceTable
from app.policy import SQLPolicy, SQLPolicyError
from app.service import QueryService


def create_app(runtime_settings=settings) -> FastAPI:
    engine = create_engine_for_url(runtime_settings.database_url)
    if runtime_settings.app_env.lower() in ("development", "test", "demo"):
        initialize_demo_database(engine)
    catalog = Catalog(engine, runtime_settings.allowed_tables)
    policy = SQLPolicy(
        catalog,
        runtime_settings.sql_dialect,
        runtime_settings.max_rows,
        runtime_settings.sensitive_columns,
    )
    model = build_model(
        runtime_settings.llm_base_url,
        runtime_settings.llm_api_key,
        runtime_settings.llm_model,
        runtime_settings.llm_timeout_seconds,
    )
    service = QueryService(
        engine,
        catalog,
        model,
        policy,
        AuditLogger(runtime_settings.audit_log_path),
        runtime_settings.catalog_top_k,
    )

    application = FastAPI(
        title="Enterprise Text-to-SQL",
        version="0.2.0",
        description="Policy-enforced natural-language access to read-only analytics data.",
    )

    @application.get("/health")
    def health():
        return {"status": "ok", "model": model.name, "tables": len(catalog.tables)}

    @application.get("/v1/catalog", response_model=List[SourceTable])
    def get_catalog():
        return catalog.public(runtime_settings.sensitive_columns)

    @application.post("/v1/query", response_model=QueryResponse)
    def query(request: QueryRequest):
        try:
            return service.answer(request)
        except SQLPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LLMError:
            raise HTTPException(status_code=502, detail="LLM provider returned an invalid response")
        except Exception:
            raise HTTPException(status_code=500, detail="Query execution failed")

    return application


app = create_app()
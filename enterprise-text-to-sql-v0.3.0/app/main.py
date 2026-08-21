from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request

from app.audit import AuditLogger
from app.auth import AuthConfig, JWTAuthenticator, Permission, RBACAuthorizer, UserContext
from app.catalog import Catalog
from app.config import settings
from app.database import create_engine_for_url, initialize_demo_database
from app.datasource import DataSourceConfig, DataSourceRegistry, DataSourceType, create_datasource
from app.llm import LLMError, build_model
from app.models import QueryRequest, QueryResponse, SourceTable
from app.permissions import create_default_permissions
from app.policy import SQLPolicy, SQLPolicyError
from app.security import IPWhitelistMiddleware, RateLimitMiddleware
from app.service import QueryService


def create_app(runtime_settings=settings) -> FastAPI:
    # Initialize primary datasource
    engine = create_engine_for_url(runtime_settings.database_url)
    if runtime_settings.app_env.lower() in ("development", "test", "demo"):
        initialize_demo_database(engine)

    # Initialize multi-datasource registry
    datasource_registry = DataSourceRegistry()
    if runtime_settings.datasources:
        for name, ds_config in runtime_settings.datasources.items():
            config = DataSourceConfig(
                name=name,
                ds_type=DataSourceType(ds_config.get("type", "sqlite")),
                connection_url=ds_config.get("url", ""),
                pool_size=ds_config.get("pool_size", 5),
                read_only=ds_config.get("read_only", True),
                ssl_required=ds_config.get("ssl_required", True),
            )
            datasource_registry.register(create_datasource(config))

    # Initialize catalog and policy
    catalog = Catalog(engine, runtime_settings.allowed_tables)
    policy = SQLPolicy(
        catalog,
        runtime_settings.sql_dialect,
        runtime_settings.max_rows,
        runtime_settings.sensitive_columns,
    )

    # Initialize LLM model
    model = build_model(
        runtime_settings.llm_base_url,
        runtime_settings.llm_api_key,
        runtime_settings.llm_model,
        runtime_settings.llm_timeout_seconds,
    )

    # Initialize authentication and authorization
    auth_config = AuthConfig(
        enabled=runtime_settings.auth_enabled,
        jwt_secret=runtime_settings.jwt_secret,
        jwt_algorithm=runtime_settings.jwt_algorithm,
        jwt_audience=runtime_settings.jwt_audience,
        jwt_issuer=runtime_settings.jwt_issuer,
        require_tenant_claim=runtime_settings.require_tenant_claim,
        tenant_claim_key=runtime_settings.tenant_claim_key,
        roles_claim_key=runtime_settings.roles_claim_key,
        permissions_claim_key=runtime_settings.permissions_claim_key,
    )
    authenticator = JWTAuthenticator(auth_config)
    authorizer = RBACAuthorizer()
    permission_engine = create_default_permissions()

    # Initialize query service
    service = QueryService(
        engine,
        catalog,
        model,
        policy,
        AuditLogger(runtime_settings.audit_log_path),
        runtime_settings.catalog_top_k,
        datasource_registry=datasource_registry if runtime_settings.datasources else None,
        permission_engine=permission_engine,
    )

    application = FastAPI(
        title="Enterprise Text-to-SQL",
        version="0.3.0",
        description="Multi-datasource policy-enforced natural-language analytics with enterprise security.",
    )

    # Add security middleware
    if runtime_settings.ip_whitelist:
        application.add_middleware(IPWhitelistMiddleware, whitelist=runtime_settings.ip_whitelist)
    application.add_middleware(RateLimitMiddleware, requests_per_minute=runtime_settings.rate_limit_per_minute)

    # Dependency for user authentication
    async def get_current_user(request: Request) -> UserContext:
        return await authenticator.authenticate(request)

    @application.get("/health")
    def health():
        datasource_health = datasource_registry.health_check_all() if datasource_registry else {}
        return {
            "status": "ok",
            "model": model.name,
            "tables": len(catalog.tables),
            "auth_enabled": runtime_settings.auth_enabled,
            "datasources": datasource_health,
        }

    @application.get("/v1/catalog", response_model=List[SourceTable])
    def get_catalog(user: UserContext = Depends(get_current_user)):
        authorizer.require_permission(user, Permission.CATALOG_READ)
        return catalog.public(runtime_settings.sensitive_columns)

    @application.post("/v1/query", response_model=QueryResponse)
    def query(request: QueryRequest, user: UserContext = Depends(get_current_user)):
        authorizer.require_permission(user, Permission.QUERY_EXECUTE)
        
        # Override request tenant_id with authenticated user's tenant
        if runtime_settings.auth_enabled:
            request.tenant_id = user.tenant_id
            request.user_id = user.user_id
        
        try:
            return service.answer(request, user_context=user)
        except SQLPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LLMError:
            raise HTTPException(status_code=502, detail="LLM provider returned an invalid response")
        except Exception:
            raise HTTPException(status_code=500, detail="Query execution failed")

    @application.get("/v1/datasources")
    def list_datasources(user: UserContext = Depends(get_current_user)):
        authorizer.require_permission(user, Permission.ADMIN_MANAGE)
        if datasource_registry:
            return {"datasources": list(datasource_registry._datasources.keys())}
        return {"datasources": ["primary"]}

    return application


app = create_app()

"""JWT/OIDC authentication and RBAC authorization."""
import time
from typing import Dict, List, Optional, Set

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel


class UserContext(BaseModel):
    """User identity and permissions extracted from JWT."""

    user_id: str
    tenant_id: str
    roles: List[str] = []
    permissions: List[str] = []
    email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuthConfig:
    """Authentication configuration."""

    def __init__(
        self,
        enabled: bool = False,
        jwt_secret: str = "",
        jwt_algorithm: str = "HS256",
        jwt_audience: Optional[str] = None,
        jwt_issuer: Optional[str] = None,
        oidc_discovery_url: Optional[str] = None,
        require_tenant_claim: bool = True,
        tenant_claim_key: str = "tenant_id",
        roles_claim_key: str = "roles",
        permissions_claim_key: str = "permissions",
    ):
        self.enabled = enabled
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_audience = jwt_audience
        self.jwt_issuer = jwt_issuer
        self.oidc_discovery_url = oidc_discovery_url
        self.require_tenant_claim = require_tenant_claim
        self.tenant_claim_key = tenant_claim_key
        self.roles_claim_key = roles_claim_key
        self.permissions_claim_key = permissions_claim_key


class JWTAuthenticator:
    """JWT token validation and user context extraction."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self.security = HTTPBearer(auto_error=False)

    async def authenticate(self, request: Request) -> Optional[UserContext]:
        """Extract and validate JWT from request."""
        if not self.config.enabled:
            return self._create_anonymous_context(request)

        credentials: Optional[HTTPAuthorizationCredentials] = await self.security(request)
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing authentication token")

        try:
            payload = jwt.decode(
                credentials.credentials,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm],
                audience=self.config.jwt_audience,
                issuer=self.config.jwt_issuer,
            )
        except JWTError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

        # Check expiration
        exp = payload.get("exp")
        if exp and exp < time.time():
            raise HTTPException(status_code=401, detail="Token expired")

        # Extract claims
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Missing 'sub' claim in token")

        tenant_id = payload.get(self.config.tenant_claim_key, "")
        if self.config.require_tenant_claim and not tenant_id:
            raise HTTPException(
                status_code=403, detail=f"Missing '{self.config.tenant_claim_key}' claim"
            )

        roles = payload.get(self.config.roles_claim_key, [])
        if isinstance(roles, str):
            roles = [roles]

        permissions = payload.get(self.config.permissions_claim_key, [])
        if isinstance(permissions, str):
            permissions = [permissions]

        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id or "default",
            roles=roles,
            permissions=permissions,
            email=payload.get("email"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    def _create_anonymous_context(self, request: Request) -> UserContext:
        """Create anonymous user context when auth is disabled."""
        return UserContext(
            user_id="anonymous",
            tenant_id="demo",
            roles=["anonymous"],
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )


class Permission:
    """Permission constants."""

    QUERY_EXECUTE = "query:execute"
    QUERY_EXPLAIN = "query:explain"
    CATALOG_READ = "catalog:read"
    ADMIN_MANAGE = "admin:manage"


class RBACAuthorizer:
    """Role-based access control."""

    def __init__(self, role_permissions: Optional[Dict[str, List[str]]] = None):
        self.role_permissions = role_permissions or {
            "admin": [Permission.QUERY_EXECUTE, Permission.QUERY_EXPLAIN, Permission.CATALOG_READ, Permission.ADMIN_MANAGE],
            "analyst": [Permission.QUERY_EXECUTE, Permission.QUERY_EXPLAIN, Permission.CATALOG_READ],
            "viewer": [Permission.CATALOG_READ],
            "anonymous": [Permission.QUERY_EXECUTE, Permission.CATALOG_READ],
        }

    def get_effective_permissions(self, user: UserContext) -> Set[str]:
        """Compute effective permissions from roles and direct permissions."""
        effective = set(user.permissions)
        for role in user.roles:
            effective.update(self.role_permissions.get(role, []))
        return effective

    def authorize(self, user: UserContext, required_permission: str) -> bool:
        """Check if user has required permission."""
        effective = self.get_effective_permissions(user)
        return required_permission in effective

    def require_permission(self, user: UserContext, required_permission: str):
        """Raise HTTPException if user lacks permission."""
        if not self.authorize(user, required_permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires '{required_permission}'",
            )


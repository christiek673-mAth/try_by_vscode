"""Tests for enterprise authentication and authorization."""
import pytest
from fastapi.testclient import TestClient

from app.auth import Permission, RBACAuthorizer, UserContext
from app.config import Settings
from app.main import create_app


def test_anonymous_user_has_basic_permissions():
    """Test that anonymous users can query when auth is disabled."""
    settings = Settings(auth_enabled=False)
    app = create_app(settings)
    client = TestClient(app)
    
    response = client.post("/v1/query", json={"question": "查询客户", "tenant_id": "demo"})
    assert response.status_code == 200


def test_rbac_authorizer_computes_effective_permissions():
    """Test permission aggregation from roles."""
    authorizer = RBACAuthorizer()
    user = UserContext(
        user_id="test",
        tenant_id="demo",
        roles=["analyst"],
        permissions=[]
    )
    
    effective = authorizer.get_effective_permissions(user)
    assert Permission.QUERY_EXECUTE in effective
    assert Permission.CATALOG_READ in effective
    assert Permission.ADMIN_MANAGE not in effective


def test_rbac_denies_missing_permission():
    """Test that missing permissions raise 403."""
    from fastapi import HTTPException
    
    authorizer = RBACAuthorizer()
    user = UserContext(
        user_id="test",
        tenant_id="demo",
        roles=["viewer"],
        permissions=[]
    )
    
    with pytest.raises(HTTPException) as exc_info:
        authorizer.require_permission(user, Permission.QUERY_EXECUTE)
    
    assert exc_info.value.status_code == 403
    assert "Permission denied" in exc_info.value.detail


def test_admin_has_all_permissions():
    """Test that admin role has full access."""
    authorizer = RBACAuthorizer()
    user = UserContext(
        user_id="admin",
        tenant_id="demo",
        roles=["admin"],
        permissions=[]
    )
    
    assert authorizer.authorize(user, Permission.QUERY_EXECUTE)
    assert authorizer.authorize(user, Permission.CATALOG_READ)
    assert authorizer.authorize(user, Permission.ADMIN_MANAGE)

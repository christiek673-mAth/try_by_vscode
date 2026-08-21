"""Tests for dynamic permission engine."""
from app.auth import UserContext
from app.permissions import DataPermission, PermissionEngine


def test_permission_matches_wildcard():
    """Test wildcard matching in permissions."""
    perm = DataPermission(tenant_id="*", datasource="*", table="*")
    
    assert perm.matches("tenant1", "ds1", "table1")
    assert perm.matches("tenant2", "ds2", "table2")


def test_permission_matches_specific_table():
    """Test specific table matching."""
    perm = DataPermission(tenant_id="demo", datasource="primary", table="customers")
    
    assert perm.matches("demo", "primary", "customers")
    assert not perm.matches("demo", "primary", "orders")
    assert not perm.matches("other", "primary", "customers")


def test_permission_engine_filters_columns():
    """Test column filtering based on permissions."""
    engine = PermissionEngine()
    user = UserContext(user_id="test", tenant_id="demo", roles=["analyst"])
    
    perm = DataPermission(
        tenant_id="demo",
        datasource="primary",
        table="customers",
        denied_columns=["email", "phone"],
    )
    engine.register_role_permissions("analyst", [perm])
    
    all_columns = ["id", "name", "email", "phone", "address"]
    allowed = engine.filter_allowed_columns(user, "primary", "customers", all_columns)
    
    assert "name" in allowed
    assert "address" in allowed
    assert "email" not in allowed
    assert "phone" not in allowed


def test_permission_engine_checks_table_access():
    """Test table access control."""
    engine = PermissionEngine()
    user = UserContext(user_id="test", tenant_id="demo", roles=["viewer"])
    
    perm = DataPermission(tenant_id="demo", datasource="primary", table="public_data")
    engine.register_role_permissions("viewer", [perm])
    
    assert engine.check_table_access(user, "primary", "public_data") is not None
    assert engine.check_table_access(user, "primary", "sensitive_data") is None

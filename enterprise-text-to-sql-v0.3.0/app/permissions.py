"""Dynamic table and column permissions for multi-tenant access control."""
from typing import Dict, List, Optional, Set

from app.auth import UserContext


class DataPermission:
    """Fine-grained data access permission."""

    def __init__(
        self,
        tenant_id: str = "*",
        datasource: str = "*",
        table: str = "*",
        allowed_columns: Optional[List[str]] = None,
        denied_columns: Optional[List[str]] = None,
        row_filter: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.datasource = datasource
        self.table = table
        self.allowed_columns = set(col.lower() for col in (allowed_columns or []))
        self.denied_columns = set(col.lower() for col in (denied_columns or []))
        self.row_filter = row_filter

    def matches(self, tenant_id: str, datasource: str, table: str) -> bool:
        """Check if permission applies to given resource."""
        return (
            (self.tenant_id == "*" or self.tenant_id == tenant_id)
            and (self.datasource == "*" or self.datasource == datasource)
            and (self.table == "*" or self.table.lower() == table.lower())
        )


class PermissionEngine:
    """Dynamic permission evaluation engine."""

    def __init__(self):
        self._role_permissions: Dict[str, List[DataPermission]] = {}
        self._user_permissions: Dict[str, List[DataPermission]] = {}

    def register_role_permissions(self, role: str, permissions: List[DataPermission]):
        """Register permissions for a role."""
        self._role_permissions[role] = permissions

    def register_user_permissions(self, user_id: str, permissions: List[DataPermission]):
        """Register user-specific permissions."""
        self._user_permissions[user_id] = permissions

    def get_effective_permissions(self, user: UserContext) -> List[DataPermission]:
        """Compute effective permissions from roles and user overrides."""
        permissions = []
        for role in user.roles:
            permissions.extend(self._role_permissions.get(role, []))
        permissions.extend(self._user_permissions.get(user.user_id, []))
        return permissions

    def check_table_access(
        self, user: UserContext, datasource: str, table: str
    ) -> Optional[DataPermission]:
        """Check if user can access table, return matching permission."""
        permissions = self.get_effective_permissions(user)
        for perm in permissions:
            if perm.matches(user.tenant_id, datasource, table):
                return perm
        return None

    def filter_allowed_columns(
        self, user: UserContext, datasource: str, table: str, columns: List[str]
    ) -> Set[str]:
        """Return subset of columns user can access."""
        perm = self.check_table_access(user, datasource, table)
        if not perm:
            return set()

        columns_lower = {col.lower() for col in columns}

        # If allowed_columns is specified, use it as whitelist
        if perm.allowed_columns:
            result = columns_lower & perm.allowed_columns
        else:
            result = columns_lower

        # Remove denied columns
        if perm.denied_columns:
            result -= perm.denied_columns

        return result

    def get_row_filter(
        self, user: UserContext, datasource: str, table: str
    ) -> Optional[str]:
        """Get row-level filter for table access."""
        perm = self.check_table_access(user, datasource, table)
        return perm.row_filter if perm else None


# Default permission configurations
def create_default_permissions() -> PermissionEngine:
    """Create permission engine with default enterprise policies."""
    engine = PermissionEngine()

    # Admin: full access to all tables
    engine.register_role_permissions(
        "admin",
        [
            DataPermission(
                tenant_id="*",
                datasource="*",
                table="*",
                allowed_columns=None,
                denied_columns=None,
            )
        ],
    )

    # Analyst: access to analytics tables, sensitive columns masked
    engine.register_role_permissions(
        "analyst",
        [
            DataPermission(
                tenant_id="*",
                datasource="*",
                table="customers",
                denied_columns=["email", "phone", "ssn", "id_card"],
            ),
            DataPermission(
                tenant_id="*",
                datasource="*",
                table="orders",
                denied_columns=["customer_email"],
            ),
        ],
    )

    # Viewer: read-only access to non-sensitive tables
    engine.register_role_permissions(
        "viewer",
        [
            DataPermission(
                tenant_id="*",
                datasource="*",
                table="products",
            ),
            DataPermission(
                tenant_id="*",
                datasource="*",
                table="categories",
            ),
        ],
    )

    return engine

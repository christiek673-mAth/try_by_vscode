"""Multi-datasource adapter with connection pooling and health checks."""
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, QueuePool


class DataSourceType(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"
    SNOWFLAKE = "snowflake"
    SQLITE = "sqlite"


class DataSourceConfig:
    """Configuration for a single data source."""

    def __init__(
        self,
        name: str,
        ds_type: DataSourceType,
        connection_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        read_only: bool = True,
        ssl_required: bool = True,
        statement_timeout_ms: int = 30000,
    ):
        self.name = name
        self.ds_type = ds_type
        self.connection_url = connection_url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.read_only = read_only
        self.ssl_required = ssl_required
        self.statement_timeout_ms = statement_timeout_ms


class DataSource(ABC):
    """Abstract data source with health check and connection management."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.engine: Optional[Engine] = None
        self._last_health_check = 0.0
        self._is_healthy = False

    @abstractmethod
    def create_engine(self) -> Engine:
        """Create SQLAlchemy engine with datasource-specific configuration."""
        pass

    def get_engine(self) -> Engine:
        """Get or create engine with lazy initialization."""
        if self.engine is None:
            self.engine = self.create_engine()
        return self.engine

    def health_check(self, force: bool = False) -> bool:
        """Check datasource health with caching."""
        now = time.time()
        if not force and (now - self._last_health_check) < 60:
            return self._is_healthy

        try:
            engine = self.get_engine()
            with engine.connect() as conn:
                conn.execute(text(self._health_check_query()))
            self._is_healthy = True
        except Exception:
            self._is_healthy = False
        finally:
            self._last_health_check = now

        return self._is_healthy

    @abstractmethod
    def _health_check_query(self) -> str:
        """Return datasource-specific health check query."""
        pass

    def dispose(self):
        """Dispose connection pool."""
        if self.engine:
            self.engine.dispose()
            self.engine = None


class DataSourceRegistry:
    """Registry for managing multiple datasources."""

    def __init__(self):
        self._datasources: Dict[str, DataSource] = {}

    def register(self, datasource: DataSource):
        """Register a datasource."""
        self._datasources[datasource.config.name] = datasource

    def get(self, name: str) -> DataSource:
        """Get datasource by name."""
        if name not in self._datasources:
            raise ValueError(f"Datasource '{name}' not found")
        return self._datasources[name]

    def get_engine(self, name: str) -> Engine:
        """Get engine for datasource."""
        return self.get(name).get_engine()

    def health_check_all(self) -> Dict[str, bool]:
        """Check health of all datasources."""
        return {name: ds.health_check() for name, ds in self._datasources.items()}

    def dispose_all(self):
        """Dispose all connection pools."""
        for ds in self._datasources.values():
            ds.dispose()


class PostgreSQLDataSource(DataSource):
    def create_engine(self) -> Engine:
        connect_args = {}
        if self.config.ssl_required:
            connect_args["sslmode"] = "require"

        engine = create_engine(
            self.config.connection_url,
            poolclass=QueuePool,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_recycle=self.config.pool_recycle,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            with dbapi_conn.cursor() as cursor:
                cursor.execute(f"SET statement_timeout = {self.config.statement_timeout_ms}")
                if self.config.read_only:
                    cursor.execute("SET default_transaction_read_only = on")

        return engine

    def _health_check_query(self) -> str:
        return "SELECT 1"


class MySQLDataSource(DataSource):
    def create_engine(self) -> Engine:
        connect_args = {}
        if self.config.ssl_required:
            connect_args["ssl"] = {"check_hostname": False}

        engine = create_engine(
            self.config.connection_url,
            poolclass=QueuePool,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_recycle=self.config.pool_recycle,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            with dbapi_conn.cursor() as cursor:
                timeout_sec = self.config.statement_timeout_ms // 1000
                cursor.execute(f"SET SESSION max_execution_time = {timeout_sec * 1000}")
                if self.config.read_only:
                    cursor.execute("SET SESSION TRANSACTION READ ONLY")

        return engine

    def _health_check_query(self) -> str:
        return "SELECT 1"


class SnowflakeDataSource(DataSource):
    def create_engine(self) -> Engine:
        return create_engine(
            self.config.connection_url,
            poolclass=QueuePool,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_recycle=self.config.pool_recycle,
            pool_pre_ping=True,
        )

    def _health_check_query(self) -> str:
        return "SELECT CURRENT_VERSION()"


class SQLiteDataSource(DataSource):
    def create_engine(self) -> Engine:
        return create_engine(
            self.config.connection_url,
            poolclass=NullPool if ":memory:" in self.config.connection_url else QueuePool,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

    def _health_check_query(self) -> str:
        return "SELECT 1"


def create_datasource(config: DataSourceConfig) -> DataSource:
    """Factory for creating datasources."""
    mapping = {
        DataSourceType.POSTGRESQL: PostgreSQLDataSource,
        DataSourceType.MYSQL: MySQLDataSource,
        DataSourceType.SNOWFLAKE: SnowflakeDataSource,
        DataSourceType.SQLITE: SQLiteDataSource,
    }

    ds_class = mapping.get(config.ds_type)
    if not ds_class:
        raise ValueError(f"Unsupported datasource type: {config.ds_type}")

    return ds_class(config)

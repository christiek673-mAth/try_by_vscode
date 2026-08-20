"""Tests for multi-datasource support."""
from app.datasource import (
    DataSourceConfig,
    DataSourceRegistry,
    DataSourceType,
    SQLiteDataSource,
    create_datasource,
)


def test_datasource_registry_manages_multiple_sources():
    """Test registering and retrieving multiple datasources."""
    registry = DataSourceRegistry()
    
    config1 = DataSourceConfig(
        name="primary",
        ds_type=DataSourceType.SQLITE,
        connection_url="sqlite:///:memory:",
        read_only=True,
    )
    config2 = DataSourceConfig(
        name="secondary",
        ds_type=DataSourceType.SQLITE,
        connection_url="sqlite:///:memory:",
        read_only=True,
    )
    
    registry.register(create_datasource(config1))
    registry.register(create_datasource(config2))
    
    assert registry.get("primary") is not None
    assert registry.get("secondary") is not None


def test_datasource_health_check():
    """Test datasource health checking."""
    config = DataSourceConfig(
        name="test",
        ds_type=DataSourceType.SQLITE,
        connection_url="sqlite:///:memory:",
    )
    ds = create_datasource(config)
    
    assert ds.health_check() is True


def test_create_datasource_factory():
    """Test datasource factory creates correct types."""
    sqlite_config = DataSourceConfig(
        name="sqlite_test",
        ds_type=DataSourceType.SQLITE,
        connection_url="sqlite:///:memory:",
    )
    
    ds = create_datasource(sqlite_config)
    assert isinstance(ds, SQLiteDataSource)
    assert ds.config.name == "sqlite_test"

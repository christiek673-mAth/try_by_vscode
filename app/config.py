import json
from typing import List

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/demo.db"
    sql_dialect: str = "sqlite"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(30.0, gt=0, le=120)
    max_rows: int = Field(200, gt=0, le=5000)
    catalog_top_k: int = Field(8, gt=0, le=50)
    sensitive_columns: List[str] = Field(default_factory=lambda: ["email", "phone", "id_card"])
    allowed_tables: List[str] = Field(default_factory=list)
    audit_log_path: str = "./data/audit.jsonl"

    @validator("sensitive_columns", "allowed_tables", pre=True)
    def split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = ""

        @classmethod
        def parse_env_var(cls, field_name, raw_val):
            if field_name in ("sensitive_columns", "allowed_tables"):
                value = raw_val.strip()
                if value.startswith("["):
                    return json.loads(value)
                return [item.strip() for item in value.split(",") if item.strip()]
            return super().parse_env_var(field_name, raw_val)


settings = Settings()
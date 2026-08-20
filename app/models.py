from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    tenant_id: str = Field("demo", min_length=1, max_length=100)
    user_id: str = Field("anonymous", min_length=1, max_length=100)
    execute: bool = True
    max_rows: Optional[int] = Field(None, ge=1, le=5000)

    @validator("question", "tenant_id", "user_id")
    def trim_values(cls, value):
        return value.strip()


class SourceTable(BaseModel):
    name: str
    description: str = ""
    columns: List[Dict[str, Any]]
    score: float = 0.0


class QueryResponse(BaseModel):
    request_id: str
    question: str
    sql: str
    explanation: str
    sources: List[SourceTable]
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_ms: Optional[float] = None
    model: str
    warnings: List[str] = Field(default_factory=list)
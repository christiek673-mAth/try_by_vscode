import json
from typing import Tuple

import httpx

class LLMError(RuntimeError):
    """Raised when the model cannot return a valid Text-to-SQL response."""


class TextToSQLModel:
    name = "unknown"

    def generate(self, question: str, context: str, tenant_id: str) -> Tuple[str, str]:
        raise NotImplementedError


class OpenAICompatibleModel(TextToSQLModel):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = model
        self.timeout = timeout

    def generate(self, question: str, context: str, tenant_id: str) -> Tuple[str, str]:
        system = (
            "You are an enterprise Text-to-SQL generator. Return JSON only with keys "
            "sql and explanation. Generate exactly one read-only SQL query. Use only "
            "tables and columns in the schema. Never select sensitive columns unless "
            "explicitly requested. Do not add tenant filters; the policy layer injects "
            "the authorized tenant scope. Never invent data."
        )
        user = (
            "Schema:\n{context}\n\nQuestion: {question}\n"
            "Use at most 200 rows.".format(context=context, question=question)
        )
        try:
            response = httpx.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + self.api_key},
                json={
                    "model": self.name,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = self._parse(content)
            return parsed["sql"], parsed.get("explanation", "")
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise LLMError("LLM request failed: {}".format(exc))

    @staticmethod
    def _parse(content: str):
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").replace("json\n", "", 1).strip()
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("sql"), str):
            raise ValueError("LLM response must contain a SQL string")
        return parsed


class MockModel(TextToSQLModel):
    """Deterministic local model used for smoke tests and first-run demos."""

    name = "mock-local"

    def generate(self, question: str, context: str, tenant_id: str) -> Tuple[str, str]:
        lowered = question.lower()
        if any(word in lowered for word in ("客户", "customer")):
            sql = "SELECT id, name, email FROM customers ORDER BY id"
            return sql, "查询客户基础信息，并按客户编号排序。"
        sql = "SELECT order_date, product, amount FROM orders ORDER BY order_date DESC"
        return sql, "查询当前租户的订单明细，并按日期倒序排列。"


def build_model(base_url: str, api_key: str, model: str, timeout: float = 30.0) -> TextToSQLModel:
    if base_url and api_key and model:
        return OpenAICompatibleModel(base_url, api_key, model, timeout)
    return MockModel()
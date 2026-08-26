"""法律知识殿堂的本地 Web API 和单页对话界面。"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request

from app.rag import LegalRAGPipeline


def create_app(pipeline: LegalRAGPipeline | None = None) -> Flask:
    """创建 Web 应用；API Key 仅由服务端环境变量读取。"""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.json.ensure_ascii = False
    app.config["LEGAL_PIPELINE"] = pipeline or LegalRAGPipeline()

    @app.get("/")
    def home() -> str:
        return render_template("index.html")

    @app.get("/api/health")
    def health() -> tuple[Any, int]:
        current_pipeline: LegalRAGPipeline = app.config["LEGAL_PIPELINE"]
        try:
            current_pipeline.load_vector_store()
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            return jsonify({"ready": False, "message": str(error)}), 503
        return jsonify({"ready": True, "collection": current_pipeline.collection_name}), 200

    @app.post("/api/chat")
    def chat() -> tuple[Any, int]:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "请求必须是 JSON 对象。"}), 400
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            return jsonify({"error": "question 必须是非空字符串。"}), 400
        top_k = payload.get("top_k", 5)
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            return jsonify({"error": "top_k 必须是整数。"}), 400
        if not 1 <= top_k <= 12:
            return jsonify({"error": "top_k 必须在 1 到 12 之间。"}), 400
        legal_status = payload.get("legal_status")
        if legal_status is not None and not isinstance(legal_status, str):
            return jsonify({"error": "legal_status 必须是字符串。"}), 400
        history = payload.get("history", [])
        if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
            return jsonify({"error": "history 必须是对象数组。"}), 400
        try:
            current_pipeline: LegalRAGPipeline = app.config["LEGAL_PIPELINE"]
            result = current_pipeline.answer(question, top_k=top_k, legal_status=legal_status, history=history)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            return jsonify({"error": str(error)}), 503
        return jsonify(result.to_dict()), 200

    return app


app = create_app()
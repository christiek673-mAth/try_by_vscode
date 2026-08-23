"""法律知识殿堂的向量索引、检索与 LCEL 问答链。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any, Sequence

from langchain_core.documents import Document


LEGAL_SYSTEM_PROMPT = """你是“法律知识殿堂”的法典检索助手，服务对象是法律工作者。

必须遵守以下规则：
1. 仅以“检索到的法条上下文”为依据；不能从上下文推出的事实、法律结论、法条内容或条文序号，必须明确说明“现有检索结果不足以支持该结论”。
2. 每一项法律判断都要紧随引用，格式为：⚖️ [法律名称 · 层级路径 · 具体法条]。不得编造引用。
3. 将“法律层级”视为条文语义的一部分：不可丢弃或改写法律名称、编、章、节和条号。
4. 用“规则（大前提）—事实适用（小前提）—暂定结论”的三段论组织回答。事实不完整时，列出需要核实的关键事实。
5. 本回答用于法律检索辅助，不替代执业律师的独立法律意见。

## 检索到的法条上下文
{context}
"""


@dataclass(frozen=True)
class EmbeddingSettings:
    model_name: str = "BAAI/bge-small-zh-v1.5"
    device: str = "cpu"


class LegalRAGPipeline:
    """ChromaDB + BGE + OpenAI 兼容模型的法规 RAG 管线。"""

    def __init__(
        self,
        persist_directory: str | Path = "data/chroma",
        collection_name: str = "chinese_laws",
        embedding_settings: EmbeddingSettings | None = None,
    ):
        self.persist_directory = Path(persist_directory).expanduser().resolve()
        self.collection_name = collection_name
        self.embedding_settings = embedding_settings or EmbeddingSettings()
        self._embeddings: Any | None = None
        self.vector_store: Any | None = None
        self.rag_chain = None

    @property
    def manifest_path(self) -> Path:
        return self.persist_directory / "index-manifest.json"

    @property
    def embeddings(self) -> Any:
        """延迟加载模型，确保纯 Markdown 解析和单元测试不下载大模型。"""
        if self._embeddings is None:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
            except ImportError as error:
                raise RuntimeError(
                    "缺少嵌入依赖。请在项目目录执行 `python -m pip install -r requirements.txt`。"
                ) from error
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_settings.model_name,
                model_kwargs={"device": self.embedding_settings.device},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def build_vector_store(self, documents: Sequence[Document], reset: bool = False) -> int:
        """按来源增量写入 Chroma；变更或删除来源时清理其陈旧向量。"""
        if reset:
            shutil.rmtree(self.persist_directory, ignore_errors=True)
        if not documents:
            if reset:
                self.persist_directory.mkdir(parents=True, exist_ok=True)
                self._write_manifest({})
                return 0
            raise ValueError("没有可写入的法条 Document。")

        chroma_class = self._chroma_class()
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.vector_store = chroma_class(
            collection_name=self.collection_name,
            persist_directory=str(self.persist_directory),
            embedding_function=self.embeddings,
        )
        documents_by_source = self._documents_by_source(documents)
        manifest = {} if reset else self._load_manifest()
        for source, source_documents in documents_by_source.items():
            source_sha256 = str(source_documents[0].metadata.get("source_sha256", ""))
            if manifest.get(source, {}).get("source_sha256") == source_sha256:
                continue
            self._delete_source(source)
            self.vector_store.add_documents(
                documents=source_documents,
                ids=[str(document.metadata["document_id"]) for document in source_documents],
            )
            manifest[source] = self._manifest_entry(source_documents)

        for deleted_source in set(manifest) - set(documents_by_source):
            self._delete_source(deleted_source)
            del manifest[deleted_source]
        self._write_manifest(manifest)
        return len(documents)

    def load_vector_store(self) -> Any:
        """加载已有 Chroma 集合；目录不存在时给出明确的索引指引。"""
        if not self.persist_directory.exists():
            raise FileNotFoundError(
                f"向量库不存在：{self.persist_directory}。请先执行 `python -m app.cli index --source-dir <法规目录>`。"
            )
        self.vector_store = self._chroma_class()(
            collection_name=self.collection_name,
            persist_directory=str(self.persist_directory),
            embedding_function=self.embeddings,
        )
        return self.vector_store

    @staticmethod
    def format_documents(documents: Sequence[Document]) -> str:
        """将召回结果转成可审计的提示词上下文，保留来源和完整目录路径。"""
        if not documents:
            return "未检索到可用法条。"
        blocks = []
        for index, document in enumerate(documents, start=1):
            metadata = document.metadata
            blocks.append(
                "\n".join(
                    (
                        f"--- [法条依据 {index}] ---",
                        f"来源: {metadata.get('source', '未知来源')}",
                        f"权威来源: {metadata.get('source_url', '') or '未提供'}",
                        f"效力状态: {metadata.get('legal_status', '') or '未提供'}",
                        f"层级路径: {metadata.get('hierarchy_path', '未知层级')}",
                        document.page_content,
                    )
                )
            )
        return "\n\n".join(blocks)

    def init_rag_chain(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        top_k: int = 5,
        temperature: float = 0.1,
    ):
        """配置 LCEL 检索链，兼容 DeepSeek、Qwen 等 OpenAI API 格式服务。"""
        if top_k < 1:
            raise ValueError("top_k 必须不小于 1。")
        if self.vector_store is None:
            self.load_vector_store()

        resolved_api_key = api_key or os.getenv("LEGAL_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not resolved_api_key:
            raise ValueError("缺少 API Key；请设置 LEGAL_LLM_API_KEY 或 DEEPSEEK_API_KEY。")

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.runnables import RunnablePassthrough
            from langchain_openai import ChatOpenAI
        except ImportError as error:
            raise RuntimeError(
                "缺少问答链依赖。请在项目目录执行 `python -m pip install -r requirements.txt`。"
            ) from error

        llm = ChatOpenAI(
            model=model or os.getenv("LEGAL_LLM_MODEL", "deepseek-chat"),
            api_key=resolved_api_key,
            base_url=base_url or os.getenv("LEGAL_LLM_BASE_URL", "https://api.deepseek.com/v1"),
            temperature=temperature,
        )
        retriever = self.vector_store.as_retriever(search_type="similarity", search_kwargs={"k": top_k})
        prompt = ChatPromptTemplate.from_messages(
            [("system", LEGAL_SYSTEM_PROMPT), ("human", "{question}")]
        )
        self.rag_chain = (
            {"context": retriever | self.format_documents, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        return self.rag_chain

    def query(self, question: str) -> str:
        if not question.strip():
            raise ValueError("问题不能为空。")
        if self.rag_chain is None:
            raise ValueError("RAG 链尚未初始化；请先调用 init_rag_chain()。")
        return self.rag_chain.invoke(question)

    @staticmethod
    def _documents_by_source(documents: Sequence[Document]) -> dict[str, list[Document]]:
        grouped: dict[str, list[Document]] = {}
        for document in documents:
            source = str(document.metadata["source"])
            grouped.setdefault(source, []).append(document)
        return grouped

    def _delete_source(self, source: str) -> None:
        """通过 Chroma metadata where 条件清理某个来源的全部历史片段。"""
        assert self.vector_store is not None
        self.vector_store.delete(where={"source": source})

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_path.is_file():
            return {}
        try:
            contents = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"索引清单已损坏：{self.manifest_path}") from error
        if not isinstance(contents, dict):
            raise ValueError(f"索引清单格式无效：{self.manifest_path}")
        return contents

    def _write_manifest(self, manifest: dict[str, dict[str, Any]]) -> None:
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _manifest_entry(documents: Sequence[Document]) -> dict[str, Any]:
        metadata = documents[0].metadata
        return {
            "source_sha256": str(metadata.get("source_sha256", "")),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "document_count": len(documents),
            "revision_version": str(metadata.get("revision_version", "")),
            "last_updated_at": str(metadata.get("last_updated_at", "")),
            "source_url": str(metadata.get("source_url", "")),
        }

    @staticmethod
    def _chroma_class() -> Any:
        try:
            from langchain_chroma import Chroma
        except ImportError as error:
            raise RuntimeError(
                "缺少 Chroma 依赖。请在项目目录执行 `python -m pip install -r requirements.txt`。"
            ) from error
        return Chroma
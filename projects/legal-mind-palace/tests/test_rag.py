from pathlib import Path

import pytest

from langchain_core.documents import Document

from app.rag import IndexProfileMismatchError, LegalRAGPipeline


def test_format_documents_keeps_source_hierarchy_and_enriched_content():
    document = Document(
        page_content="【法律层级】中华人民共和国民法典 > 第一编 总则 > 第十八条\n【条文内容】\n成年人为完全民事行为能力人。",
        metadata={"source": "法律/民法典.md", "hierarchy_path": "中华人民共和国民法典 > 第一编 总则 > 第十八条"},
    )

    context = LegalRAGPipeline.format_documents([document])

    assert "--- [法条依据 1 / C1] ---" in context
    assert "引用资料" in context
    assert "来源: 法律/民法典.md" in context
    assert "层级路径: 中华人民共和国民法典 > 第一编 总则 > 第十八条" in context
    assert document.page_content in context


def test_format_documents_reports_empty_retrieval():
    assert LegalRAGPipeline.format_documents([]) == "未检索到可用法条。"


def test_format_documents_keeps_legal_metadata_when_available():
    document = Document(
        page_content="测试内容",
        metadata={
            "source": "法律/测试法.md",
            "hierarchy_path": "测试法 > 第一条",
            "source_url": "https://example.test/law",
            "legal_status": "现行有效",
        },
    )

    context = LegalRAGPipeline.format_documents([document])

    assert "权威来源: https://example.test/law" in context
    assert "效力状态: 现行有效" in context


class FakeVectorStore:
    def __init__(self):
        self.added_ids: list[str] = []
        self.deleted_sources: list[str] = []

    def add_documents(self, documents, ids):
        self.added_ids.extend(ids)

    def delete(self, where):
        self.deleted_sources.append(where["source"])


def test_incremental_index_replaces_changed_source_and_removes_deleted_source(tmp_path, monkeypatch):
    stores: list[FakeVectorStore] = []

    def chroma_class(**_kwargs):
        store = FakeVectorStore()
        stores.append(store)
        return store

    pipeline = LegalRAGPipeline(persist_directory=tmp_path / "chroma")
    monkeypatch.setattr(pipeline, "_chroma_class", lambda: chroma_class)
    monkeypatch.setattr(type(pipeline), "embeddings", property(lambda _self: object()))
    first = Document(page_content="first", metadata={"source": "a.md", "source_sha256": "one", "document_id": "1"})
    second = Document(page_content="second", metadata={"source": "a.md", "source_sha256": "two", "document_id": "2"})

    pipeline.build_vector_store([first])
    pipeline.build_vector_store([second])
    pipeline.build_vector_store([second])

    assert stores[0].added_ids == ["1"]
    assert stores[1].deleted_sources == ["a.md"]
    assert stores[1].added_ids == ["2"]
    assert stores[2].deleted_sources == []
    manifest = Path(pipeline.manifest_path).read_text(encoding="utf-8")
    assert '"source_sha256": "two"' in manifest

    pipeline.build_vector_store([Document(page_content="other", metadata={"source": "b.md", "source_sha256": "three", "document_id": "3"})])
    assert stores[3].deleted_sources == ["b.md", "a.md"]


def test_reset_allows_an_empty_source_set_and_replaces_manifest(tmp_path):
    pipeline = LegalRAGPipeline(persist_directory=tmp_path / "chroma")
    pipeline.manifest_path.parent.mkdir(parents=True)
    pipeline.manifest_path.write_text(
        '{"schema_version": 2, "profile": {}, "sources": {"old.md": {}}}', encoding="utf-8"
    )

    assert pipeline.build_vector_store([], reset=True) == 0
    assert '"sources": {}' in pipeline.manifest_path.read_text(encoding="utf-8")


def test_incremental_index_reindexes_when_legal_metadata_changes(tmp_path, monkeypatch):
    stores: list[FakeVectorStore] = []

    def chroma_class(**_kwargs):
        store = FakeVectorStore()
        stores.append(store)
        return store

    pipeline = LegalRAGPipeline(persist_directory=tmp_path / "chroma")
    monkeypatch.setattr(pipeline, "_chroma_class", lambda: chroma_class)
    monkeypatch.setattr(type(pipeline), "embeddings", property(lambda _self: object()))
    old = Document(
        page_content="第一条",
        metadata={"source": "a.md", "source_sha256": "same", "document_id": "1", "legal_status": "现行有效"},
    )
    new = Document(
        page_content="第一条",
        metadata={"source": "a.md", "source_sha256": "same", "document_id": "2", "legal_status": "已废止"},
    )

    pipeline.build_vector_store([old])
    pipeline.build_vector_store([new])

    assert stores[1].deleted_sources == ["a.md"]
    assert stores[1].added_ids == ["2"]


def test_index_profile_change_requires_reset(tmp_path, monkeypatch):
    pipeline = LegalRAGPipeline(persist_directory=tmp_path / "chroma")
    monkeypatch.setattr(pipeline, "_chroma_class", lambda: lambda **_kwargs: FakeVectorStore())
    monkeypatch.setattr(type(pipeline), "embeddings", property(lambda _self: object()))
    document = Document(page_content="第一条", metadata={"source": "a.md", "source_sha256": "one", "document_id": "1"})
    pipeline.build_vector_store([document])
    changed = LegalRAGPipeline(persist_directory=tmp_path / "chroma", max_article_chars=900)

    with pytest.raises(IndexProfileMismatchError, match="索引配置"):
        changed.build_vector_store([document])
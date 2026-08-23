from langchain_core.documents import Document

from app.rag import LegalRAGPipeline


def test_format_documents_keeps_source_hierarchy_and_enriched_content():
    document = Document(
        page_content="【法律层级】中华人民共和国民法典 > 第一编 总则 > 第十八条\n【条文内容】\n成年人为完全民事行为能力人。",
        metadata={"source": "法律/民法典.md", "hierarchy_path": "中华人民共和国民法典 > 第一编 总则 > 第十八条"},
    )

    context = LegalRAGPipeline.format_documents([document])

    assert "--- [法条依据 1] ---" in context
    assert "来源: 法律/民法典.md" in context
    assert "层级路径: 中华人民共和国民法典 > 第一编 总则 > 第十八条" in context
    assert document.page_content in context


def test_format_documents_reports_empty_retrieval():
    assert LegalRAGPipeline.format_documents([]) == "未检索到可用法条。"
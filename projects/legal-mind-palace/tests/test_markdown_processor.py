from app.markdown_processor import LegalMarkdownProcessor


MARKDOWN = """# 中华人民共和国民法典

## 第一编 总则

### 第二章 自然人

#### 第一节 民事权利能力和民事行为能力

##### 第十八条
成年人为完全民事行为能力人，可以独立实施民事法律行为。

十六周岁以上的未成年人，以自己的劳动收入为主要生活来源的，视为完全民事行为能力人。

##### 第十九条
八周岁以上的未成年人为限制民事行为能力人。

### 第三章 法人

##### 第五十七条
法人是具有民事权利能力和民事行为能力，依法独立享有民事权利和承担民事义务的组织。
"""


def test_process_markdown_preserves_article_and_full_parent_hierarchy():
    documents = LegalMarkdownProcessor().process_markdown(MARKDOWN, source_path="法律/民法典.md")

    assert len(documents) == 3
    eighteenth = documents[0]
    assert eighteenth.metadata["source"] == "法律/民法典.md"
    assert eighteenth.metadata["article"] == "第十八条"
    assert eighteenth.metadata["hierarchy_path"] == (
        "中华人民共和国民法典 > 第一编 总则 > 第二章 自然人 > "
        "第一节 民事权利能力和民事行为能力 > 第十八条"
    )
    assert eighteenth.page_content.startswith(f"【法律层级】{eighteenth.metadata['hierarchy_path']}\n【条文内容】")
    assert "成年人为完全民事行为能力人" in eighteenth.page_content
    assert "十六周岁以上的未成年人" in eighteenth.page_content

    fifty_seventh = documents[2]
    assert fifty_seventh.metadata["chapter"] == "第三章 法人"
    assert fifty_seventh.metadata["section"] == ""
    assert "第一节 民事权利能力" not in fifty_seventh.metadata["hierarchy_path"]


def test_processor_recognizes_plain_article_lines_and_article_subnumber():
    markdown = """# 测试法

## 第一章 总则

第十条之一 附加规则
本条规定适用于测试情形。
"""
    documents = LegalMarkdownProcessor().process_markdown(markdown)

    assert len(documents) == 1
    assert documents[0].metadata["article"] == "第十条之一"
    assert documents[0].metadata["hierarchy_path"] == "测试法 > 第一章 总则 > 第十条之一"
    assert "第十条之一 附加规则" in documents[0].page_content


def test_processor_recognizes_article_when_it_uses_a_level_one_markdown_heading():
    markdown = """# 测试法

## 第一章 总则

# 第一条
本条使用一级 Markdown 标题，但仍必须被解析为法条。
"""
    documents = LegalMarkdownProcessor().process_markdown(markdown)

    assert len(documents) == 1
    assert documents[0].metadata["law_name"] == "测试法"
    assert documents[0].metadata["article"] == "第一条"
    assert documents[0].metadata["hierarchy_path"] == "测试法 > 第一章 总则 > 第一条"


def test_long_article_is_split_at_paragraph_boundaries_with_hierarchy_repeated():
    markdown = """# 测试法

## 第一章 总则

### 第一条
第一段规定甲的权利和义务。

第二段规定乙的权利和义务。

第三段规定丙的权利和义务。
"""
    documents = LegalMarkdownProcessor(max_article_chars=20, overlap_paragraphs=0).process_markdown(markdown)

    assert len(documents) == 3
    assert {document.metadata["chunk_count"] for document in documents} == {3}
    assert [document.metadata["chunk_index"] for document in documents] == [1, 2, 3]
    assert len({document.metadata["hierarchy_path"] for document in documents}) == 1
    assert all(document.page_content.startswith("【法律层级】测试法 > 第一章 总则 > 第一条") for document in documents)
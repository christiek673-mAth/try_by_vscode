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


def test_processor_keeps_unnumbered_markdown_divisions_and_source_metadata():
    markdown = """# 测试条例

## 总则

### 适用范围

#### 第一条
本条例适用于测试事项。

## 附则

#### 第二条
本条例自公布之日起施行。
"""
    documents = LegalMarkdownProcessor().process_markdown(
        markdown,
        source_path="条例/测试条例.md",
        source_metadata={
            "issuing_authority": "测试机关",
            "effective_date": "2026-01-01",
            "legal_status": "现行有效",
            "source_url": "https://example.test/law",
            "source_sha256": "source-hash",
        },
    )

    assert documents[0].metadata["hierarchy_path"] == "测试条例 > 总则 > 适用范围 > 第一条"
    assert documents[1].metadata["hierarchy_path"] == "测试条例 > 附则 > 第二条"
    assert documents[0].metadata["issuing_authority"] == "测试机关"
    assert documents[0].metadata["effective_date"] == "2026-01-01"
    assert documents[0].metadata["legal_status"] == "现行有效"
    assert documents[0].metadata["source_url"] == "https://example.test/law"
    assert documents[0].metadata["source_sha256"] == "source-hash"


def test_processor_reads_law_dataset_json_snapshot_records(tmp_path):
    source = tmp_path / "laws.json"
    source.write_text(
        """[
  {
    "id": "npc-1",
    "title": "测试法",
    "office": "全国人民代表大会",
    "publish": "2025-12-01 00:00:00",
    "expiry": "",
    "status": "1",
    "url": "https://flk.npc.gov.cn/detail2.html?id=npc-1",
    "content": "# 测试法\\n\\n## 总则\\n\\n### 第一条\\n测试法条内容。"
  }
]""",
        encoding="utf-8",
    )

    documents = LegalMarkdownProcessor().process_file(source, tmp_path)

    assert len(documents) == 1
    document = documents[0]
    assert document.metadata["source"] == "laws.json"
    assert document.metadata["source_record_id"] == "npc-1"
    assert document.metadata["law_name"] == "测试法"
    assert document.metadata["issuing_authority"] == "全国人民代表大会"
    assert document.metadata["promulgation_date"] == "2025-12-01 00:00:00"
    assert document.metadata["legal_status"] == "1"
    assert document.metadata["source_url"] == "https://flk.npc.gov.cn/detail2.html?id=npc-1"
    assert document.metadata["source_sha256"]


def test_processor_resets_hierarchy_when_one_markdown_file_contains_multiple_laws():
    markdown = """# 测试法甲

## 总则

### 第一条
甲法条内容。

# 测试法乙

## 附则

### 第一条
乙法条内容。
"""

    documents = LegalMarkdownProcessor().process_markdown(markdown)

    assert [document.metadata["law_name"] for document in documents] == ["测试法甲", "测试法乙"]
    assert [document.metadata["hierarchy_path"] for document in documents] == [
        "测试法甲 > 总则 > 第一条",
        "测试法乙 > 附则 > 第一条",
    ]


def test_processor_reports_unfetched_git_lfs_pointer_as_invalid_zip(tmp_path):
    source = tmp_path / "laws.json.zip"
    source.write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")

    try:
        LegalMarkdownProcessor().process_file(source, tmp_path)
    except ValueError as error:
        assert "Git LFS" in str(error)
    else:
        raise AssertionError("未下载的 Git LFS 指针必须被拒绝。")
import json

import pytest

from app.cli import build_parser, load_metadata_by_source, prepare_p0_catalog, validate_catalog_sources
from app.markdown_processor import LegalMarkdownProcessor


def test_load_metadata_by_source_reads_source_mapping(tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(
        json.dumps({"法律/测试法.md": {"legal_status": "现行有效"}}, ensure_ascii=False), encoding="utf-8"
    )

    assert load_metadata_by_source(metadata_file) == {"法律/测试法.md": {"legal_status": "现行有效"}}


def test_load_metadata_by_source_rejects_invalid_shape(tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="相对来源路径"):
        load_metadata_by_source(metadata_file)


def test_runtime_options_can_be_placed_after_subcommand():
    args = build_parser().parse_args(
        ["index", "--source-dir", "laws", "--db-dir", "custom-db", "--device", "mps"]
    )

    assert str(args.db_dir) == "custom-db"
    assert args.device == "mps"


def test_prepare_p0_catalog_copies_template_and_creates_source_directory(tmp_path):
    source_dir, metadata_file = prepare_p0_catalog(tmp_path / "laws", tmp_path / "catalogs" / "p0.json")

    assert source_dir.is_dir()
    contents = load_metadata_by_source(metadata_file)
    assert len(contents) == 20
    assert "中央法律/中华人民共和国民法典.md" in contents


def test_validate_catalog_sources_requires_complete_verified_matching_laws(tmp_path):
    source = tmp_path / "中央法律" / "中华人民共和国测试法.md"
    source.parent.mkdir()
    source.write_text("# 中华人民共和国测试法\n\n## 第一章 总则\n\n### 第一条\n测试内容。\n", encoding="utf-8")
    catalog = {
        "中央法律/中华人民共和国测试法.md": {
            "title": "中华人民共和国测试法",
            "legal_status": "现行有效",
            "source_url": "https://example.test/law",
        }
    }

    assert validate_catalog_sources(tmp_path, catalog, LegalMarkdownProcessor()) == []

    catalog["中央法律/中华人民共和国测试法.md"]["legal_status"] = "待核验"
    errors = validate_catalog_sources(tmp_path, catalog, LegalMarkdownProcessor())
    assert "必须人工核验" in errors[0]
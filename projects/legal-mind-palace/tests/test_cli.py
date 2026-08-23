import json

import pytest

from app.cli import load_metadata_by_source


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
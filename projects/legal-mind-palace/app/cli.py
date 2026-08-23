"""法律知识殿堂命令行入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from app.markdown_processor import LegalMarkdownProcessor, iter_sources
from app.rag import EmbeddingSettings, LegalRAGPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="法律知识殿堂：保留法规目录层级的 RAG 索引与问答工具")
    parser.add_argument("--db-dir", type=Path, default=Path("data/chroma"), help="Chroma 持久化目录")
    parser.add_argument("--collection", default="chinese_laws", help="Chroma collection 名称")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5", help="BGE 嵌入模型名称")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "mps"), help="嵌入模型运行设备")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index = subparsers.add_parser("index", help="递归解析并索引法规 Markdown")
    index.add_argument("--source-dir", type=Path, required=True, help="法规 Markdown 根目录")
    index.add_argument("--reset", action="store_true", help="删除已有 collection 后全量重建")
    index.add_argument("--max-article-chars", type=int, default=1800, help="超长法条的最大字符数")
    index.add_argument(
        "--metadata-file",
        type=Path,
        help="可选 JSON：以相对来源路径为 key 的法规元数据映射，用于补充发布机关、效力状态等字段",
    )

    query = subparsers.add_parser("query", help="检索法规并调用 OpenAI 兼容模型回答")
    query.add_argument("--question", required=True, help="待分析的法律问题")
    query.add_argument("--api-key", help="模型 API Key；默认读取环境变量")
    query.add_argument("--base-url", help="OpenAI 兼容 API 地址")
    query.add_argument("--model", help="模型名称，如 deepseek-chat 或 qwen-plus")
    query.add_argument("--top-k", type=int, default=5, help="召回法条数")
    return parser


def pipeline_from_args(args: argparse.Namespace) -> LegalRAGPipeline:
    return LegalRAGPipeline(
        persist_directory=args.db_dir,
        collection_name=args.collection,
        embedding_settings=EmbeddingSettings(model_name=args.embedding_model, device=args.device),
    )


def load_metadata_by_source(metadata_file: Path | None) -> dict[str, dict[str, Any]]:
    """读取 ``{相对来源路径: {法规元数据}}`` 格式的可选补充元数据。"""
    if metadata_file is None:
        return {}
    try:
        contents = json.loads(metadata_file.expanduser().read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ValueError(f"无法读取法规元数据文件：{metadata_file}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"法规元数据 JSON 格式无效：{metadata_file}") from error
    if not isinstance(contents, dict) or not all(isinstance(value, dict) for value in contents.values()):
        raise ValueError("法规元数据文件必须是 {相对来源路径: {字段: 值}} 形式的 JSON 对象。")
    return {str(source): value for source, value in contents.items()}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = pipeline_from_args(args)
    if args.command == "index":
        processor = LegalMarkdownProcessor(max_article_chars=args.max_article_chars)
        documents = processor.process_directory(args.source_dir, load_metadata_by_source(args.metadata_file))
        indexed = pipeline.build_vector_store(documents, reset=args.reset)
        print(f"索引完成：{indexed} 个法条片段，来自 {len(iter_sources(documents))} 个法规来源文件。")
        return 0

    pipeline.init_rag_chain(
        api_key=args.api_key, base_url=args.base_url, model=args.model, top_k=args.top_k
    )
    print(pipeline.query(args.question))
    return 0


if __name__ == "__main__":
    sys.exit(main())
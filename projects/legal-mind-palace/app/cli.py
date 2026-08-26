"""法律知识殿堂命令行入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from app.markdown_processor import LegalMarkdownProcessor, iter_sources
from app.rag import EmbeddingSettings, LegalRAGPipeline


def _add_runtime_options(parser: argparse.ArgumentParser, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--db-dir", type=Path, default=default, help="Chroma 持久化目录")
    parser.add_argument("--collection", default=default, help="Chroma collection 名称")
    parser.add_argument("--embedding-model", default=default, help="BGE 嵌入模型名称")
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default=default, help="嵌入模型运行设备")


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
    _add_runtime_options(index, suppress_defaults=True)

    query = subparsers.add_parser("query", help="检索法规并调用 OpenAI 兼容模型回答")
    _add_runtime_options(query, suppress_defaults=True)
    query.add_argument("--question", required=True, help="待分析的法律问题")
    query.add_argument("--api-key", help="模型 API Key；默认读取环境变量")
    query.add_argument("--base-url", help="OpenAI 兼容 API 地址")
    query.add_argument("--model", help="模型名称，如 deepseek-chat 或 qwen-plus")
    query.add_argument("--top-k", type=int, default=5, help="召回法条数")
    query.add_argument("--legal-status", help="仅检索指定原始效力状态")
    query.add_argument("--max-article-chars", type=int, default=1800, help="建库时使用的法条切分长度")

    validate = subparsers.add_parser("validate", help="解析并报告语料，不写入向量库")
    validate.add_argument("--source-dir", type=Path, required=True, help="法规根目录")
    validate.add_argument("--max-article-chars", type=int, default=1800)
    validate.add_argument("--metadata-file", type=Path)
    validate.add_argument(
        "--catalog-file",
        type=Path,
        help="可选法规目录清单 JSON；校验清单中的文件是否齐全、标题是否一致，并拒绝清单外法规文件",
    )

    prepare_p0 = subparsers.add_parser("prepare-p0", help="准备首批中央法律 P0 本地导入目录和元数据清单")
    prepare_p0.add_argument(
        "--source-dir",
        type=Path,
        default=Path("data/authorized-laws"),
        help="存放经人工核验法规原文的本地目录",
    )
    prepare_p0.add_argument(
        "--metadata-file",
        type=Path,
        default=Path("data/catalogs/central-laws-p0.json"),
        help="输出的 P0 元数据清单路径",
    )
    prepare_p0.add_argument("--force", action="store_true", help="覆盖已有元数据清单")

    serve = subparsers.add_parser("serve", help="启动本地网页对话服务")
    _add_runtime_options(serve, suppress_defaults=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--debug", action="store_true")
    serve.add_argument("--max-article-chars", type=int, default=1800, help="建库时使用的法条切分长度")
    return parser


def pipeline_from_args(args: argparse.Namespace) -> LegalRAGPipeline:
    return LegalRAGPipeline(
        persist_directory=args.db_dir,
        collection_name=args.collection,
        embedding_settings=EmbeddingSettings(model_name=args.embedding_model, device=args.device),
        max_article_chars=getattr(args, "max_article_chars", 1800),
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


def validate_catalog_sources(
    source_dir: Path, catalog_by_source: dict[str, dict[str, Any]], processor: LegalMarkdownProcessor
) -> list[str]:
    """校验法规目录清单和本地原文，避免将错误版本或无来源文本混入 P0 索引。"""
    root = source_dir.expanduser().resolve()
    expected_sources = set(catalog_by_source)
    actual_sources = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.suffix.lower() in {".md", ".markdown"}
    }
    missing_sources = sorted(expected_sources - actual_sources)
    unexpected_sources = sorted(actual_sources - expected_sources)
    errors: list[str] = []
    if missing_sources:
        errors.append(f"缺少 {len(missing_sources)} 个清单法规文件：{', '.join(missing_sources)}")
    if unexpected_sources:
        errors.append(f"发现 {len(unexpected_sources)} 个清单外法规文件：{', '.join(unexpected_sources)}")

    for source in sorted(expected_sources & actual_sources):
        metadata = catalog_by_source[source]
        title = str(metadata.get("title", "")).strip()
        source_url = str(metadata.get("source_url", "")).strip()
        legal_status = str(metadata.get("legal_status", "")).strip()
        if not title:
            errors.append(f"{source} 缺少 title。")
            continue
        if not source_url.startswith("https://"):
            errors.append(f"{source} 的 source_url 必须是 HTTPS 官方详情页 URL。")
        if legal_status != "现行有效":
            errors.append(f"{source} 的 legal_status 必须人工核验为“现行有效”，当前为“{legal_status or '空'}”。")
        documents = processor.process_file(root / source, root, metadata)
        law_names = {str(document.metadata["law_name"]) for document in documents}
        if law_names != {title}:
            errors.append(f"{source} 的 H1 标题应为“{title}”，实际解析为：{', '.join(sorted(law_names)) or '无'}。")
    return errors


def prepare_p0_catalog(source_dir: Path, metadata_file: Path, force: bool = False) -> tuple[Path, Path]:
    """复制版本受控的 P0 清单到本地忽略目录，并创建法规正文目录。"""
    template = Path(__file__).resolve().parent.parent / "catalogs" / "central-laws-p0.json"
    if not template.is_file():
        raise FileNotFoundError(f"未找到内置 P0 清单：{template}")
    source_dir = source_dir.expanduser()
    metadata_file = metadata_file.expanduser()
    source_dir.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    if metadata_file.exists() and not force:
        raise ValueError(f"P0 元数据清单已存在：{metadata_file}；如需覆盖请使用 --force。")
    shutil.copyfile(template, metadata_file)
    return source_dir.resolve(), metadata_file.resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            processor = LegalMarkdownProcessor(max_article_chars=args.max_article_chars)
            metadata_by_source = load_metadata_by_source(args.metadata_file)
            if args.catalog_file:
                catalog_by_source = load_metadata_by_source(args.catalog_file)
                if metadata_by_source and metadata_by_source != catalog_by_source:
                    raise ValueError("同时指定 --metadata-file 与 --catalog-file 时，两份清单必须完全一致。")
                metadata_by_source = catalog_by_source
                errors = validate_catalog_sources(args.source_dir, catalog_by_source, processor)
                if errors:
                    raise ValueError("P0 法规目录校验失败：\n- " + "\n- ".join(errors))
            documents = processor.process_directory(args.source_dir, metadata_by_source)
            print(f"语料校验通过：{len(documents)} 个法条片段，来自 {len(iter_sources(documents))} 个来源文件。")
            return 0
        if args.command == "prepare-p0":
            source_dir, metadata_file = prepare_p0_catalog(args.source_dir, args.metadata_file, args.force)
            print("P0 法规导入目录已准备完成。法规原文未随项目提供，必须逐份从官方来源人工核验后保存。")
            print(f"法规目录：{source_dir}")
            print(f"元数据清单：{metadata_file}")
            print("完成后执行：python -m app.cli validate --source-dir <法规目录> --catalog-file <元数据清单>")
            return 0
        if args.command == "serve":
            from app.web import create_app

            create_app(pipeline_from_args(args)).run(host=args.host, port=args.port, debug=args.debug)
            return 0

        pipeline = pipeline_from_args(args)
        if args.command == "index":
            processor = LegalMarkdownProcessor(max_article_chars=args.max_article_chars)
            documents = processor.process_directory(args.source_dir, load_metadata_by_source(args.metadata_file))
            indexed = pipeline.build_vector_store(documents, reset=args.reset)
            print(f"索引完成：{indexed} 个法条片段，来自 {len(iter_sources(documents))} 个法规来源文件。")
            return 0

        result = pipeline.answer(
            args.question,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
            top_k=args.top_k,
            legal_status=args.legal_status,
        )
        print(result.answer)
        for citation in result.citations:
            print(f"\n[{citation.citation_id}] {citation.hierarchy_path} | {citation.source_url or citation.source}")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        build_parser().error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
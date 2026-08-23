"""将法规 Markdown 解析为带完整层级上下文的 LangChain Document。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from zipfile import BadZipFile, ZipFile

from langchain_core.documents import Document


ARTICLE_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?P<article>第[〇零一二三四五六七八九十百千万亿\d]+条(?:之[〇零一二三四五六七八九十百千万亿\d]+)?)"
    r"(?P<title>.*)$"
)
HEADING_PATTERN = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
DIVISION_PATTERN = re.compile(
    r"^(?P<division>第[〇零一二三四五六七八九十百千万亿\d]+(?P<kind>编|章|节))\s*(?P<title>.*)$"
)
DIVISION_KEYS = {"编": "part", "章": "chapter", "节": "section"}
HEADING_LEVEL_KEYS = {2: "part", 3: "chapter", 4: "section"}
LEGAL_METADATA_FIELDS = (
    "issuing_authority",
    "document_number",
    "promulgation_date",
    "effective_date",
    "expiration_date",
    "legal_status",
    "revision_version",
    "last_updated_at",
    "source_url",
    "jurisdiction",
)


@dataclass
class LegalHierarchy:
    """正在解析的法规目录树；下级节点变更时会清空全部后代。"""

    law_name: str
    part: str = ""
    chapter: str = ""
    section: str = ""

    def update_division(self, kind: str, value: str) -> None:
        key = DIVISION_KEYS[kind]
        setattr(self, key, value)
        if key == "part":
            self.chapter = ""
            self.section = ""
        elif key == "chapter":
            self.section = ""

    def path(self, article: str = "") -> str:
        return " > ".join(
            value
            for value in (self.law_name, self.part, self.chapter, self.section, article)
            if value
        )

    def update_heading(self, level: int, value: str) -> bool:
        """将未编号的 Markdown 目录按相对标题级别映射为法规层级。"""
        key = HEADING_LEVEL_KEYS.get(level)
        if key is None:
            return False
        setattr(self, key, value)
        if key == "part":
            self.chapter = ""
            self.section = ""
        elif key == "chapter":
            self.section = ""
        return True


@dataclass
class ArticleBuffer:
    article: str
    title: str
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        first_line = " ".join(value for value in (self.article, self.title) if value).rstrip()
        body = "\n".join(self.lines).strip()
        return f"{first_line}\n{body}".strip()


class LegalMarkdownProcessor:
    """法规 Markdown 解析器。

    解析器不使用按字符数直接切片的策略。每一条法规先保持完整；只有当一条
    法规超过 ``max_article_chars`` 时，才在段落边界切分，并为每一个片段重复
    注入同一条法规及其父级目录，避免检索和生成时失去语义归属。
    """

    def __init__(self, max_article_chars: int = 1800, overlap_paragraphs: int = 1):
        if max_article_chars < 1:
            raise ValueError("max_article_chars 必须为正整数。")
        if overlap_paragraphs < 0:
            raise ValueError("overlap_paragraphs 不能为负数。")
        self.max_article_chars = max_article_chars
        self.overlap_paragraphs = overlap_paragraphs

    def process_directory(
        self, source_dir: str | Path, metadata_by_source: Mapping[str, Mapping[str, Any]] | None = None
    ) -> list[Document]:
        """递归读取 Markdown，以及 ``laws.json`` / ``laws.json.zip`` 形式的法规快照。"""
        root = Path(source_dir).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"法规目录不存在：{root}")

        files = sorted(
            path
            for path in root.rglob("*")
            if path.suffix.lower() in {".md", ".markdown", ".json"} or path.name.lower().endswith(".json.zip")
        )
        metadata_by_source = metadata_by_source or {}
        documents: list[Document] = []
        for path in files:
            relative_path = self._relative_source_path(path, root)
            documents.extend(self.process_file(path, root, metadata_by_source.get(relative_path)))
        return documents

    def process_file(
        self,
        file_path: str | Path,
        source_root: str | Path | None = None,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> list[Document]:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"法规文件不存在：{path}")
        relative_path = self._relative_source_path(path, source_root)
        file_sha256 = self._file_sha256(path)
        metadata = self._normalize_metadata(source_metadata, source_sha256=file_sha256)
        if path.name.lower().endswith(".json.zip"):
            return self._process_json_zip(path, relative_path, metadata)
        if path.suffix.lower() == ".json":
            return self._process_json_text(path.read_text(encoding="utf-8-sig"), relative_path, metadata)
        text = path.read_text(encoding="utf-8-sig")
        return self.process_markdown(
            text,
            source_path=relative_path,
            fallback_law_name=path.stem,
            source_metadata=metadata,
        )

    def process_markdown(
        self,
        markdown_text: str,
        source_path: str = "memory.md",
        fallback_law_name: str = "未知法规",
        source_metadata: Mapping[str, Any] | None = None,
        document_identity: str | None = None,
    ) -> list[Document]:
        """将一个 Markdown 文本解析成可索引的完整法条 Document。"""
        law_name = self._find_law_name(markdown_text, fallback_law_name)
        hierarchy = LegalHierarchy(law_name=law_name)
        documents: list[Document] = []
        article_buffer: ArticleBuffer | None = None
        preamble: list[str] = []

        def flush_article() -> None:
            nonlocal article_buffer
            if article_buffer is None:
                return
            article_text = article_buffer.render()
            if article_text:
                documents.extend(
                    self._documents_for_article(
                        article_text=article_text,
                        hierarchy=hierarchy,
                        article=article_buffer.article,
                        source_path=source_path,
                        source_metadata=source_metadata,
                        document_identity=document_identity,
                    )
                )
            article_buffer = None

        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip()
            heading = HEADING_PATTERN.match(line)
            candidate = heading.group("title").strip() if heading else line.strip()

            division = self._division(candidate)
            if division:
                flush_article()
                kind, value = division
                hierarchy.update_division(kind, value)
                continue

            article_match = ARTICLE_PATTERN.match(candidate)
            if article_match:
                flush_article()
                article_buffer = ArticleBuffer(
                    article=article_match.group("article"), title=article_match.group("title").strip()
                )
                continue

            if heading and heading.group("marks") == "#":
                # H1 通常是法律名称。必须在识别法条之后处理，兼容少量以 # 标记条号的文件。
                flush_article()
                hierarchy = LegalHierarchy(law_name=candidate)
                continue

            if heading:
                # 实务语料常用“总则”“附则”等无编号标题；标题前的法条必须先落盘。
                heading_level = len(heading.group("marks"))
                if heading_level in HEADING_LEVEL_KEYS:
                    flush_article()
                    hierarchy.update_heading(heading_level, candidate)
                    continue

            if article_buffer is not None:
                article_buffer.lines.append(raw_line)
            elif candidate and not heading:
                preamble.append(raw_line)

        flush_article()
        if not documents and "\n".join(preamble).strip():
            documents.extend(
                self._documents_for_article(
                    article_text="\n".join(preamble).strip(),
                    hierarchy=hierarchy,
                    article="",
                    source_path=source_path,
                    chunk_kind="preamble",
                    source_metadata=source_metadata,
                    document_identity=document_identity,
                )
            )
        return documents

    @staticmethod
    def _find_law_name(markdown_text: str, fallback_law_name: str) -> str:
        for line in markdown_text.splitlines():
            heading = HEADING_PATTERN.match(line.rstrip())
            if heading and heading.group("marks") == "#":
                return heading.group("title").strip()
        return fallback_law_name.strip() or "未知法规"

    @staticmethod
    def _division(text: str) -> tuple[str, str] | None:
        match = DIVISION_PATTERN.match(text)
        if not match:
            return None
        return match.group("kind"), f"{match.group('division')} {match.group('title').strip()}".rstrip()

    @staticmethod
    def _relative_source_path(path: Path, source_root: str | Path | None) -> str:
        if source_root is None:
            return path.name
        root = Path(source_root).expanduser().resolve()
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name

    def _documents_for_article(
        self,
        article_text: str,
        hierarchy: LegalHierarchy,
        article: str,
        source_path: str,
        chunk_kind: str = "article",
        source_metadata: Mapping[str, Any] | None = None,
        document_identity: str | None = None,
    ) -> list[Document]:
        chunks = self._split_long_article(article_text)
        path = hierarchy.path(article)
        base_metadata = {
            "source": source_path,
            "law_name": hierarchy.law_name,
            "part": hierarchy.part,
            "chapter": hierarchy.chapter,
            "section": hierarchy.section,
            "article": article,
            "hierarchy_path": path,
            "chunk_kind": chunk_kind,
            "chunk_count": len(chunks),
            **self._normalize_metadata(source_metadata),
        }
        docs = []
        for index, chunk in enumerate(chunks, start=1):
            document_id = self._document_id(document_identity or source_path, path, index, chunk)
            metadata = {**base_metadata, "chunk_index": index, "document_id": document_id}
            enhanced_content = f"【法律层级】{path}\n【条文内容】\n{chunk}"
            docs.append(Document(page_content=enhanced_content, metadata=metadata))
        return docs

    def _process_json_zip(
        self, path: Path, source_path: str, source_metadata: Mapping[str, Any]
    ) -> list[Document]:
        try:
            with ZipFile(path) as archive:
                json_names = [name for name in archive.namelist() if name.lower().endswith(".json")]
                if len(json_names) != 1:
                    raise ValueError("压缩包中必须恰有一个 JSON 文件。")
                text = archive.read(json_names[0]).decode("utf-8-sig")
        except (BadZipFile, OSError) as error:
            raise ValueError(f"无法读取法规 JSON 压缩包：{path}；请确认 Git LFS 数据已实际下载。") from error
        return self._process_json_text(text, source_path, source_metadata)

    def _process_json_text(
        self, text: str, source_path: str, source_metadata: Mapping[str, Any]
    ) -> list[Document]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"法规 JSON 格式无效：{source_path}") from error
        records = payload.get("laws", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError(f"法规 JSON 顶层必须是数组或包含 laws 数组：{source_path}")

        documents: list[Document] = []
        for record_index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or not str(record.get("content", "")).strip():
                continue
            record_metadata = dict(source_metadata)
            record_metadata.update(self._metadata_from_law_record(record))
            record_metadata["source_sha256"] = str(source_metadata.get("source_sha256", ""))
            record_id = str(record.get("id") or record_index)
            documents.extend(
                self.process_markdown(
                    str(record["content"]),
                    source_path=source_path,
                    fallback_law_name=str(record.get("title") or f"法规记录 {record_id}"),
                    source_metadata=record_metadata,
                    document_identity=f"{source_path}#{record_id}",
                )
            )
        return documents

    @staticmethod
    def _metadata_from_law_record(record: Mapping[str, Any]) -> dict[str, str]:
        """映射全国人大法律法规库快照字段；未知状态保持原值，禁止猜测其法律含义。"""
        links = record.get("links") if isinstance(record.get("links"), dict) else {}
        source_url = record.get("url") or links.get("HTML") or links.get("WORD") or links.get("PDF")
        return LegalMarkdownProcessor._normalize_metadata(
            {
                "issuing_authority": record.get("office"),
                "document_number": record.get("document_number") or record.get("number"),
                "promulgation_date": record.get("publish"),
                "effective_date": record.get("effective_date") or record.get("effective"),
                "expiration_date": record.get("expiry") or record.get("expiration_date"),
                "legal_status": record.get("status"),
                "revision_version": record.get("revision_version") or record.get("version"),
                "last_updated_at": record.get("last_updated_at") or record.get("updated_at"),
                "source_url": source_url,
                "jurisdiction": record.get("jurisdiction"),
                "source_record_id": record.get("id"),
            }
        )

    @staticmethod
    def _normalize_metadata(
        metadata: Mapping[str, Any] | None = None, source_sha256: str | None = None
    ) -> dict[str, str]:
        metadata = metadata or {}
        normalized = {field: "" if metadata.get(field) is None else str(metadata.get(field)) for field in LEGAL_METADATA_FIELDS}
        normalized["source_sha256"] = source_sha256 or str(metadata.get("source_sha256", ""))
        if metadata.get("source_record_id") is not None:
            normalized["source_record_id"] = str(metadata["source_record_id"])
        return normalized

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _split_long_article(self, article_text: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", article_text) if paragraph.strip()]
        if not paragraphs:
            return []
        if len(article_text) <= self.max_article_chars:
            return [article_text]

        chunks: list[str] = []
        current: list[str] = []
        for paragraph in paragraphs:
            projected = "\n\n".join([*current, paragraph])
            if current and len(projected) > self.max_article_chars:
                chunks.append("\n\n".join(current))
                current = current[-self.overlap_paragraphs :] if self.overlap_paragraphs else []
            if len(paragraph) > self.max_article_chars:
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                chunks.extend(self._hard_split(paragraph))
            else:
                current.append(paragraph)
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _hard_split(self, paragraph: str) -> list[str]:
        """极端长段落才按中文句末标点优先切分，且不产生空片段。"""
        sentences = [item.strip() for item in re.split(r"(?<=[。；！？])", paragraph) if item.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) > self.max_article_chars:
                chunks.append(current)
                current = ""
            while len(sentence) > self.max_article_chars:
                chunks.append(sentence[: self.max_article_chars])
                sentence = sentence[self.max_article_chars :]
            current += sentence
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _document_id(source_path: str, hierarchy_path: str, chunk_index: int, content: str) -> str:
        raw = f"{source_path}\0{hierarchy_path}\0{chunk_index}\0{content}".encode("utf-8")
        return sha256(raw).hexdigest()


def iter_sources(documents: Iterable[Document]) -> set[str]:
    """返回文档集合中的稳定来源路径，便于索引后审计。"""
    return {str(document.metadata["source"]) for document in documents}
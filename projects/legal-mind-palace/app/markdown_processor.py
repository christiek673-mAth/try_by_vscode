"""将法规 Markdown 解析为带完整层级上下文的 LangChain Document。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

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

    def process_directory(self, source_dir: str | Path) -> list[Document]:
        """递归读取目录内的 ``.md`` / ``.markdown`` 法规文件。"""
        root = Path(source_dir).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"法规目录不存在：{root}")

        files = sorted(
            path for path in root.rglob("*") if path.suffix.lower() in {".md", ".markdown"}
        )
        return [document for path in files for document in self.process_file(path, root)]

    def process_file(self, file_path: str | Path, source_root: str | Path | None = None) -> list[Document]:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"法规文件不存在：{path}")
        relative_path = self._relative_source_path(path, source_root)
        text = path.read_text(encoding="utf-8-sig")
        return self.process_markdown(text, source_path=relative_path, fallback_law_name=path.stem)

    def process_markdown(
        self, markdown_text: str, source_path: str = "memory.md", fallback_law_name: str = "未知法规"
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
                if article_buffer is None:
                    hierarchy.law_name = candidate
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
        }
        docs = []
        for index, chunk in enumerate(chunks, start=1):
            document_id = self._document_id(source_path, path, index, chunk)
            metadata = {**base_metadata, "chunk_index": index, "document_id": document_id}
            enhanced_content = f"【法律层级】{path}\n【条文内容】\n{chunk}"
            docs.append(Document(page_content=enhanced_content, metadata=metadata))
        return docs

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
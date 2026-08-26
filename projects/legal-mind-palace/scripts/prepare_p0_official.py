"""从国家法律法规数据库准备本地授权研究用 P0 法律快照。

该脚本只写入被 Git 忽略的 ``data/`` 目录。正文下载前提是使用者已确认
本地内部研究授权；项目不提交法规正文，也不把下载地址当作再分发授权。
"""

from __future__ import annotations

import html
import json
import re
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = ROOT / "catalogs" / "central-laws-p0.json"
CATALOG_FILE = ROOT / "data" / "catalogs" / "central-laws-p0.json"
SOURCE_ROOT = ROOT / "data" / "authorized-laws"
DOWNLOAD_ROOT = ROOT / "data" / ".p0-downloads"
API_ROOT = "https://flk.npc.gov.cn/law-search"
HEADERS = {
    "User-Agent": "LegalMindPalace/1.0 (+local-authorized-research)",
    "Origin": "https://flk.npc.gov.cn",
    "Referer": "https://flk.npc.gov.cn/",
}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
ARTICLE_RE = re.compile(r"^第[〇零一二三四五六七八九十百千万亿0-9]+条(?:之[〇零一二三四五六七八九十百千万亿0-9]+)?(?:\s|$)")
DIVISION_RE = re.compile(r"^第[〇零一二三四五六七八九十百千万亿0-9]+(编|章|节)(?:\s|$)")


def clean_title(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


def request_json(session: requests.Session, method: str, url: str, **kwargs) -> dict:
    for attempt in range(4):
        try:
            response = session.request(method, url, timeout=(15, 90), **kwargs)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (None, 200):
                raise RuntimeError(payload)
            return payload
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def find_current_record(session: requests.Session, title: str) -> dict:
    payload = {
        "searchContent": title,
        "searchRange": 1,
        "searchType": 1,
        "sxrq": [],
        "gbrq": [],
        "sxx": [],
        "xgzlSearch": False,
    }
    result = request_json(session, "POST", f"{API_ROOT}/search/list", json=payload)
    rows = result.get("rows", [])
    matches = [
        row
        for row in rows
        if clean_title(row.get("title", "")) == title and row.get("flxz") == "法律" and row.get("sxx") == 3
    ]
    if not matches and title == "中华人民共和国宪法":
        matches = [
            row
            for row in rows
            if clean_title(row.get("title", "")).startswith(f"{title}（2018年修正文本）")
            and row.get("flxz") == "宪法"
            and row.get("sxx") == 3
        ]
    if not matches:
        raise RuntimeError(f"未找到《{title}》的标题完全匹配且现行有效记录。")
    return matches[0]


def get_detail(session: requests.Session, bbbs: str) -> dict:
    result = request_json(
        session,
        "GET",
        f"{API_ROOT}/search/flfgDetails",
        params={"bbbs": bbbs},
    )
    return result["data"]


def get_docx_url(session: requests.Session, bbbs: str) -> str:
    result = request_json(
        session,
        "GET",
        f"{API_ROOT}/download/pc",
        params={"bbbs": bbbs, "format": "docx"},
    )
    return result["data"]["url"]


def download_docx(session: requests.Session, url: str, target: Path) -> None:
    for attempt in range(4):
        try:
            response = session.get(url, timeout=(20, 180))
            response.raise_for_status()
            if not response.content.startswith(b"PK"):
                raise RuntimeError("官方下载内容不是 DOCX ZIP 文件。")
            target.write_bytes(response.content)
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.findall(".//w:body/w:p", WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NS))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def markdown_from_paragraphs(paragraphs: list[str], title: str) -> str:
    """将官方 DOCX 的正文段落转为项目 Markdown。

    国家法律法规数据库的 DOCX 通常包含题注、目录和正文。通过“第一条”连续
    出现两次来定位正文起点，避免把目录条目误当成正文；若目录不存在，则从
    第一次出现第一条开始。
    """
    first_article = next((index for index, text in enumerate(paragraphs) if ARTICLE_RE.match(text)), None)
    if first_article is None:
        raise RuntimeError(f"《{title}》官方 DOCX 未识别到法条。")
    first_article_starts = [
        index for index in range(first_article, len(paragraphs)) if paragraphs[index].startswith("第一条")
    ]
    body_start = first_article
    if len(first_article_starts) >= 2:
        # 目录第一项一般是“第一条”，正文第一项随后再次出现。
        body_start = first_article_starts[1]

    lines = [f"# {title}", ""]
    for index, text in enumerate(paragraphs[body_start:], start=body_start):
        if index == body_start and not ARTICLE_RE.match(text):
            continue
        article = ARTICLE_RE.match(text)
        division = DIVISION_RE.match(text)
        if article:
            lines.extend([f"### {text}", ""])
        elif division:
            level = {"编": 2, "章": 3, "节": 4}[division.group(1)]
            lines.extend([f"{'#' * level} {text}", ""])
        else:
            lines.extend([text, ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    catalog = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    output = {}

    for number, (source, template) in enumerate(catalog.items(), start=1):
        title = template["title"]
        print(f"[{number}/20] {title}", flush=True)
        record = find_current_record(session, title)
        detail = get_detail(session, record["bbbs"])
        if detail.get("title") != title and not (
            title == "中华人民共和国宪法" and detail.get("title") == "中华人民共和国宪法（2018年修正文本）"
        ):
            raise RuntimeError(f"官方详情标题不一致：{title} != {detail.get('title')}")

        docx_path = DOWNLOAD_ROOT / f"{record['bbbs']}.docx"
        if not docx_path.is_file():
            download_docx(session, get_docx_url(session, record["bbbs"]), docx_path)
        markdown = markdown_from_paragraphs(docx_paragraphs(docx_path), title)
        target = SOURCE_ROOT / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")

        item = dict(template)
        item.update(
            {
                "issuing_authority": detail.get("zdjgName") or record.get("zdjgName", ""),
                "promulgation_date": detail.get("gbrq") or record.get("gbrq", ""),
                "effective_date": detail.get("sxrq") or record.get("sxrq", ""),
                "legal_status": "现行有效",
                "revision_version": f"国家法律法规数据库记录（公布日期：{detail.get('gbrq') or record.get('gbrq', '')}）",
                "verified_at": "2026-08-25",
                "source_url": f"https://flk.npc.gov.cn/detail?id={record['bbbs']}&type=fl",
                "source_name": "国家法律法规数据库",
            }
        )
        output[source] = item
        print(
            f"  record={record['bbbs']} publish={item['promulgation_date']} "
            f"effective={item['effective_date']} chars={len(markdown)}",
            flush=True,
        )
        time.sleep(0.4)

    CATALOG_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入：{CATALOG_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
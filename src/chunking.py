# -*- coding: utf-8 -*-

"""PDF chapter-based chunking for HR handbook."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


CHAPTER_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百零\d]+章\s*[：:\s]*", re.MULTILINE),
    re.compile(r"^Chapter\s+\d+\s*[：:.\s]*", re.MULTILINE),
    re.compile(r"^(\d+)[.．]\s+[^\n]{2,80}$", re.MULTILINE),
]

MAX_CHUNK_CHARS = 500
OVERLAP_CHARS = 80


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract full text from PDF (all pages concatenated)."""
    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def find_chapter_splits(text: str) -> list[tuple[int, str]]:
    """
    Find positions where a new chapter/section starts.
    Returns list of (start_index, chapter_title_or_empty).
    First element is always (0, '').
    """
    splits: list[tuple[int, str]] = [(0, "")]
    for pattern in CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            start = m.start()
            if start == 0:
                continue
            title = m.group(0).strip()
            if not any(s[0] == start for s in splits):
                splits.append((start, title))
    splits.sort(key=lambda x: x[0])
    seen = set()
    unique = []
    for pos, title in splits:
        if pos not in seen:
            seen.add(pos)
            unique.append((pos, title))
    return unique


def _split_long_section(
    content: str, chapter_title: str, chapter_index: int
) -> list[dict[str, Any]]:
    """Split a long section into chunks with overlap."""
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(content):
        end = min(start + MAX_CHUNK_CHARS, len(content))
        if end < len(content):
            for sep in ["\n\n", "\n", "。", "."]:
                last = content.rfind(sep, start, end + 1)
                if last > start + MAX_CHUNK_CHARS // 2:
                    end = last + len(sep)
                    break
        chunk_text = content[start:end].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "chapter_title": chapter_title,
                "chapter_index": chapter_index,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        start = end - OVERLAP_CHARS if end < len(content) else len(content)
    return chunks


def chunk_by_chapters(pdf_path: str | Path) -> list[dict[str, Any]]:
    """
    Chunk PDF by chapters/sections. Returns list of dicts with keys:
    text, chapter_title, chapter_index, chunk_index.
    """
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return []

    splits = find_chapter_splits(text)
    if not splits:
        splits = [(0, "全文")]

    result = []
    for i in range(len(splits)):
        start, section_title = splits[i]
        end = splits[i + 1][0] if i + 1 < len(splits) else len(text)
        content = text[start:end].strip()
        if not content:
            continue
        chapter_title = section_title or f"Section_{i}"
        if len(content) <= MAX_CHUNK_CHARS:
            result.append({
                "text": content,
                "chapter_title": chapter_title,
                "chapter_index": i,
                "chunk_index": 0,
            })
        else:
            result.extend(
                _split_long_section(content, chapter_title, i)
            )
    return result


def chunk_hr_manual(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Alias for chunk_by_chapters; entry point for HR manual."""
    return chunk_by_chapters(pdf_path)

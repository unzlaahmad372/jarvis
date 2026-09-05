"""Document parsing — extract plain text from TXT, Markdown, PDF, DOCX.

Each parser returns a list of (text, page) tuples so page metadata is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


@dataclass
class ParsedPage:
    text: str
    page: int | None = None  # 1-based page number where applicable


def parse_document(path: Path) -> list[ParsedPage]:
    """Parse a document and return its text content by page/section.

    Raises:
        ValueError: Unsupported file type.
        RuntimeError: Parsing failed.
    """
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix!r}. Supported: {SUPPORTED_EXTENSIONS}")

    try:
        if suffix in (".txt", ".md"):
            return _parse_text(path)
        if suffix == ".pdf":
            return _parse_pdf(path)
        if suffix == ".docx":
            return _parse_docx(path)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Failed to parse {path.name}: {exc}") from exc

    raise ValueError(f"Unsupported: {suffix}")


def _parse_text(path: Path) -> list[ParsedPage]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return [ParsedPage(text=text, page=None)] if text else []


def _parse_pdf(path: Path) -> list[ParsedPage]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[ParsedPage] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(ParsedPage(text=text, page=i))
    return pages


def _parse_docx(path: Path) -> list[ParsedPage]:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)
    return [ParsedPage(text=text, page=None)] if text else []

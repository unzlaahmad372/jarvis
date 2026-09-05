"""Text chunker — splits parsed pages into overlapping token-budget chunks.

Uses character-based splitting with the same token estimator as ContextBuilder
so chunk sizes are consistent with context budget calculations.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.brain.context_builder import estimate_tokens
from app.knowledge.parser import ParsedPage

# Characters per token — must match context_builder._CHARS_PER_TOKEN
_CHARS_PER_TOKEN = 3.5


def _tokens_to_chars(tokens: int) -> int:
    return int(tokens * _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    content: str
    chunk_index: int   # 0-based within the document
    page: int | None
    char_start: int
    char_end: int
    token_count: int


def chunk_pages(
    pages: list[ParsedPage],
    chunk_size_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Split parsed pages into overlapping chunks.

    Each page is chunked independently so page metadata is preserved.
    """
    chunk_chars = _tokens_to_chars(chunk_size_tokens)
    overlap_chars = _tokens_to_chars(overlap_tokens)
    step = max(1, chunk_chars - overlap_chars)

    chunks: list[Chunk] = []
    global_index = 0

    for page in pages:
        text = page.text
        if not text:
            continue

        start = 0
        while start < len(text):
            end = min(start + chunk_chars, len(text))
            content = text[start:end].strip()
            if content:
                chunks.append(
                    Chunk(
                        content=content,
                        chunk_index=global_index,
                        page=page.page,
                        char_start=start,
                        char_end=end,
                        token_count=estimate_tokens(content),
                    )
                )
                global_index += 1
            start += step

    return chunks

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ChannelBookState:
    """Holds reading state for a channel.

    Attributes:
        chunks: The list of paragraph-chunks to deliver.
        index: Index of the next chunk to deliver.
        chunk_size: Number of paragraphs per chunk.
    """

    chunks: List[str]
    index: int
    chunk_size: int


def split_into_paragraphs(text: str) -> List[str]:
    """Split raw text into trimmed paragraphs, dropping empty lines and normalizing whitespace."""
    # Normalize all whitespace sequences to single spaces
    normalized_text = " ".join(text.split())
    # Split by double spaces (paragraph breaks) or by periods followed by spaces
    paragraphs = []
    current_paragraph = ""
    
    # Split by common paragraph indicators
    parts = normalized_text.replace(".  ", ".\n\n").replace("!  ", "!\n\n").replace("?  ", "?\n\n").split("\n\n")
    
    for part in parts:
        part = part.strip()
        if part and len(part) > 10:  # Only include substantial paragraphs
            paragraphs.append(part)
    
    # Fallback: if no paragraph breaks found, split by sentence
    if len(paragraphs) <= 1:
        sentences = normalized_text.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n").split("\n")
        paragraphs = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
    
    return paragraphs


def chunk_paragraphs(paragraphs: List[str], chunk_size: int) -> List[str]:
    """Group paragraphs into chunks of size chunk_size, joined with blank lines."""
    normalized_size: int = max(1, min(50, chunk_size))
    return ["\n\n".join(paragraphs[i:i + normalized_size]) for i in range(0, len(paragraphs), normalized_size)]


def rebuild_chunks_from_existing(chunks: List[str], new_chunk_size: int) -> List[str]:
    """Reconstruct paragraphs from existing chunks and re-split with new size."""
    all_paragraphs: List[str] = "\n\n".join(chunks).split("\n\n")
    return chunk_paragraphs(all_paragraphs, new_chunk_size)


def get_or_create_state(store: Dict[int, ChannelBookState], channel_id: int) -> ChannelBookState:
    """Return existing state or a new default state for a channel."""
    if channel_id not in store:
        store[channel_id] = ChannelBookState(chunks=[], index=0, chunk_size=3)
    return store[channel_id]




import hashlib
import os
import platform
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pymupdf as fitz  # PyMuPDF

IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
SUPPORTED_EXT = {".pdf", *IMAGE_MIME}


@dataclass
class LoadedDocument:
    images: list[tuple[bytes, str]]           # (image bytes, mime type)
    text: str = ""
    links: list[str] = field(default_factory=list)
    page_count: int = 1
    pdf_created_at: Optional[datetime] = None
    pdf_modified_at: Optional[datetime] = None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def filesystem_dates(path: str | Path) -> tuple[Optional[datetime], datetime]:
    """(created, modified). Creation time is only reliable on Windows/macOS."""
    st = os.stat(path)
    modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    created = None
    if hasattr(st, "st_birthtime"):
        created = datetime.fromtimestamp(st.st_birthtime, tz=timezone.utc)
    elif platform.system() == "Windows":
        created = datetime.fromtimestamp(st.st_ctime, tz=timezone.utc)
    return created, modified


_PDF_DATE = re.compile(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?")


def parse_pdf_date(value: Optional[str]) -> Optional[datetime]:
    """PDF metadata dates look like "D:20230115103000+01'00'"."""
    if not value:
        return None
    m = _PDF_DATE.match(value)
    if not m:
        return None
    defaults = (None, 1, 1, 0, 0, 0)
    parts = [int(g) if g else d for g, d in zip(m.groups(), defaults)]
    try:
        return datetime(*parts)
    except ValueError:
        return None


def load_document(path: str | Path, dpi: int = 150, max_pages: int = 6) -> LoadedDocument:
    path = Path(path)
    ext = path.suffix.lower()

    if ext in IMAGE_MIME:
        return LoadedDocument(images=[(path.read_bytes(), IMAGE_MIME[ext])], page_count=1)

    if ext != ".pdf":
        raise ValueError(f"Unsupported file type: {ext}")

    images, texts, links = [], [], []
    with fitz.open(path) as doc:
        page_count = doc.page_count
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi)
            images.append((pix.tobytes("png"), "image/png"))

            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (round(b[1]), b[0]))  # top-to-bottom, then left-to-right
            page_text = "\n".join(b[4].strip() for b in blocks if b[4].strip())
            texts.append(f"--- Page {i + 1} ---\n{page_text}")

            for link in page.get_links():
                uri = link.get("uri")
                if uri and uri not in links:
                    links.append(uri)

        meta = doc.metadata or {}

    return LoadedDocument(
        images=images,
        text="\n\n".join(texts).strip(),
        links=links,
        page_count=page_count,
        pdf_created_at=parse_pdf_date(meta.get("creationDate")),
        pdf_modified_at=parse_pdf_date(meta.get("modDate")),
    )
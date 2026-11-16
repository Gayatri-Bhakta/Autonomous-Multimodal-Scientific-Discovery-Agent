"""Upload validation and small file helpers."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Dict, Optional, Sequence


def validate_upload(name: str, data: bytes, allowed: Sequence[str], max_mb: float = 10.0) -> Optional[str]:
    """Return an error message, or None when the upload looks acceptable."""
    ext = Path(name or "").suffix.lower()
    if ext not in allowed:
        return f"'{name}' has an unsupported type {ext or '(none)'}; allowed: {', '.join(allowed)}."
    if not data:
        return f"'{name}' is empty."
    if len(data) > max_mb * 1024 * 1024:
        return f"'{name}' is {len(data) / 1_048_576:.1f} MB; the limit is {max_mb:g} MB."
    return None


def safe_filename(name: str) -> str:
    """Strip directories and odd characters (also protects against path traversal)."""
    base = Path(name or "upload").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "upload"


def save_upload(data: bytes, name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / safe_filename(name)
    path.write_bytes(data)
    return path


def read_if_exists(path: Optional[str]) -> Optional[bytes]:
    if not path:
        return None
    p = Path(path)
    return p.read_bytes() if p.is_file() else None


def make_zip(files: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()

"""Shared result type: services never raise to the UI, they return a ServiceResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    message: str = ""
    code: str = "ok"
    seconds: float = 0.0
    warnings: List[str] = field(default_factory=list)

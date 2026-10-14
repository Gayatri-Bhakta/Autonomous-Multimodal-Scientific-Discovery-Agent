"""Agents package for the Autonomous Multimodal Scientific Discovery Agent.

The main classes are exported lazily (PEP 562). This has two benefits:

* No circular imports: the three agent modules never import each other, and
  this package does not import them until a name is actually requested.
* ``python -m agents.literature_reviewer`` runs without the "module found in
  sys.modules" RuntimeWarning.

Usage::

    from agents import LiteratureReviewer, HypothesisGenerator, CodeExecutor
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = ["LiteratureReviewer", "HypothesisGenerator", "CodeExecutor"]

# Maps each exported name to the sub-module that defines it.
_EXPORTS = {
    "LiteratureReviewer": ".literature_reviewer",
    "HypothesisGenerator": ".hypothesis_generator",
    "CodeExecutor": ".code_executor",
}

if TYPE_CHECKING:  # Only for type checkers / IDE auto-complete.
    from .code_executor import CodeExecutor
    from .hypothesis_agent import HypothesisGenerator
    from .literature_agent import LiteratureReviewer


def __getattr__(name: str) -> Any:
    """Import an agent class on first access."""
    if name in _EXPORTS:
        module = importlib.import_module(_EXPORTS[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

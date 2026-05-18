from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AdapterDiagnostics:
    status: str = "ok"
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalDocument:
    source_format: str
    source_name: str
    content: dict[str, Any]
    diagnostics: AdapterDiagnostics = field(default_factory=AdapterDiagnostics)

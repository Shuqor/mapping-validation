from core.adapters.edifact_adapter import EdifactFormatAdapter
from core.adapters.json_adapter import JsonFormatAdapter
from core.adapters.pipeline import parse_with_registry
from core.adapters.registry import AdapterRegistry
from core.adapters.x12_adapter import X12FormatAdapter


def build_default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(JsonFormatAdapter())
    registry.register(X12FormatAdapter())
    registry.register(EdifactFormatAdapter())
    return registry


__all__ = [
    "AdapterRegistry",
    "EdifactFormatAdapter",
    "JsonFormatAdapter",
    "X12FormatAdapter",
    "build_default_registry",
    "parse_with_registry",
]

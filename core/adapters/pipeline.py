from core.adapters.models import CanonicalDocument
from core.adapters.registry import AdapterRegistry


def parse_with_registry(raw_payload: bytes, source_name: str, registry: AdapterRegistry) -> CanonicalDocument:
    adapter = registry.resolve_for_source(source_name)
    return adapter.parse(raw_payload=raw_payload, source_name=source_name)

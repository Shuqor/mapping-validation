from core.adapters.base import FormatAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, FormatAdapter] = {}

    def register(self, adapter: FormatAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, adapter_name: str) -> FormatAdapter:
        if adapter_name not in self._adapters:
            raise KeyError(f"Adapter not registered: {adapter_name}")
        return self._adapters[adapter_name]

    def resolve_for_source(self, source_name: str) -> FormatAdapter:
        for adapter in self._adapters.values():
            if adapter.can_handle(source_name):
                return adapter
        raise ValueError(f"No adapter can handle source: {source_name}")

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())

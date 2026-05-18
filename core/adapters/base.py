from abc import ABC, abstractmethod

from core.adapters.models import CanonicalDocument


class FormatAdapter(ABC):
    name = "base"
    supported_extensions: tuple[str, ...] = tuple()

    def can_handle(self, source_name: str) -> bool:
        lowered = source_name.lower()
        return any(lowered.endswith(ext) for ext in self.supported_extensions)

    @abstractmethod
    def parse(self, raw_payload: bytes, source_name: str) -> CanonicalDocument:
        raise NotImplementedError

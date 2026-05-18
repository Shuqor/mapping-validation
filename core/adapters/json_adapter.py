import json
from typing import Any

from core.adapters.base import FormatAdapter
from core.adapters.models import AdapterDiagnostics, CanonicalDocument


class JsonFormatAdapter(FormatAdapter):
    name = "json"
    supported_extensions = (".json",)

    def parse(self, raw_payload: bytes, source_name: str) -> CanonicalDocument:
        text = raw_payload.decode("utf-8")
        parsed = json.loads(text)

        content = {
            "root": self._normalize(parsed),
        }

        diagnostics = AdapterDiagnostics(
            status="ok",
            warnings=[],
            info=["normalized_json_tree"],
        )
        return CanonicalDocument(
            source_format=self.name,
            source_name=source_name,
            content=content,
            diagnostics=diagnostics,
        )

    def _normalize(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "type": "object",
                "fields": {
                    key: self._normalize(value[key])
                    for key in sorted(value.keys())
                },
            }
        if isinstance(value, list):
            return {
                "type": "array",
                "items": [self._normalize(item) for item in value],
            }
        if isinstance(value, bool):
            return {"type": "boolean", "value": value}
        if value is None:
            return {"type": "null", "value": None}
        if isinstance(value, (int, float)):
            return {"type": "number", "value": value}
        return {"type": "string", "value": str(value)}

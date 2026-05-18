from core.adapters.base import FormatAdapter
from core.adapters.models import AdapterDiagnostics, CanonicalDocument


class X12FormatAdapter(FormatAdapter):
    name = "x12"
    supported_extensions = (".x12",)

    def parse(self, raw_payload: bytes, source_name: str) -> CanonicalDocument:
        text = raw_payload.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("X12 payload is empty")

        element_separator = "*"
        if text.startswith("ISA") and len(text) >= 4:
            element_separator = text[3]

        segment_terminator = "~" if "~" in text else "\n"
        segments = [segment.strip() for segment in text.split(segment_terminator) if segment.strip()]

        canonical_segments = []
        for segment in segments:
            elements = segment.split(element_separator)
            tag = (elements[0] or "UNK").strip()
            element_items = []
            for value in elements[1:]:
                value = value.strip()
                if ":" in value:
                    element_items.append(
                        {
                            "type": "array",
                            "items": [{"type": "string", "value": part} for part in value.split(":")],
                        }
                    )
                else:
                    element_items.append({"type": "string", "value": value})

            canonical_segments.append(
                {
                    "type": "object",
                    "fields": {
                        "tag": {"type": "string", "value": tag},
                        "elements": {"type": "array", "items": element_items},
                    },
                }
            )

        content = {
            "root": {
                "type": "object",
                "fields": {
                    "interchange_type": {"type": "string", "value": "x12"},
                    "segments": {"type": "array", "items": canonical_segments},
                },
            }
        }

        diagnostics = AdapterDiagnostics(
            status="ok",
            warnings=[],
            info=[f"normalized_x12_segments:{len(canonical_segments)}"],
        )
        return CanonicalDocument(
            source_format=self.name,
            source_name=source_name,
            content=content,
            diagnostics=diagnostics,
        )

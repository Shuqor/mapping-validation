from pathlib import Path

import main


def test_main_uses_payload_bridge_entrypoint(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "spec.xlsx"
    input_path = tmp_path / "input.edifact"
    output_path = tmp_path / "output.json"
    report_path = tmp_path / "report.json"
    spec_path.write_bytes(b"fake spec")
    input_path.write_bytes(b"UNB+UNOA:1+SENDER+RECEIVER+240101:0101+000000001'")
    output_path.write_bytes(b'{"invoice": {"id": "1"}}')

    captured = {}

    def _stub_parse_args():
        class _Args:
            spec = str(spec_path)
            input = str(input_path)
            output = str(output_path)
            report = str(report_path)
            mode = "lenient"
        return _Args()

    def _stub_validate(spec, input_payload, input_filename, output_payload, output_filename, validation_mode="strict"):
        captured["spec"] = spec
        captured["input_payload"] = input_payload
        captured["input_filename"] = input_filename
        captured["output_payload"] = output_payload
        captured["output_filename"] = output_filename
        captured["validation_mode"] = validation_mode
        return {
            "summary": {"status": "PASS_WITH_WARNINGS", "parser_status": "clean", "parser_confidence": "high"},
            "human_summary": {"headline": "Validation completed", "issue_breakdown": [], "what_to_fix_first": []},
            "rule_support_summary": {"enforced_rules": 1, "parsed_only_rules": 0, "unsupported_rules": 0},
            "adapter_pipeline": {"enabled": True, "mode": "cross_format", "input_format": "edifact", "output_format": "json"},
            "warnings": [],
            "errors": [],
            "valid": True,
        }

    monkeypatch.setattr(main, "parse_args", _stub_parse_args)
    monkeypatch.setattr(main, "validate_mapping_from_payload_bytes", _stub_validate)
    monkeypatch.setattr(main, "write_report", lambda result, report: Path(report))

    exit_code = main.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["spec"] == str(spec_path)
    assert captured["input_filename"] == "input.edifact"
    assert captured["output_filename"] == "output.json"
    assert captured["input_payload"] == input_path.read_bytes()
    assert captured["output_payload"] == output_path.read_bytes()
    assert captured["validation_mode"] == "lenient"
    assert "Adapter pipeline: EDIFACT -> JSON (cross-format bridge)" in output
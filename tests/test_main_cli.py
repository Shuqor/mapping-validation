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
            batch_manifest = ""
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


def test_main_spec_coverage_mode_uses_spec_only_entrypoint(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "spec.xlsx"
    report_path = tmp_path / "coverage_report.json"
    spec_path.write_bytes(b"fake spec")

    captured = {}

    def _stub_parse_args():
        class _Args:
            spec = str(spec_path)
            input = "unused_input.xml"
            output = "unused_output.xml"
            report = str(report_path)
            mode = "spec_coverage"
            batch_manifest = ""
        return _Args()

    def _stub_validate_spec_coverage(spec):
        captured["spec"] = spec
        return {
            "summary": {"status": "PASS_WITH_WARNINGS", "parser_status": "parsed_with_warnings", "parser_confidence": "medium"},
            "human_summary": {"headline": "Spec coverage ready", "issue_breakdown": [], "what_to_fix_first": []},
            "rule_support_summary": {"enforced_rules": 10, "parsed_only_rules": 2, "unsupported_rules": 1},
            "rule_gap_summary": {
                "enforceable_coverage_percent": 76.92,
                "semantic_condition_coverage_percent": 90.0,
                "missing_cardinality_rules": 3,
                "next_action": "Review unsupported condition wording and add deterministic pattern handlers for remaining gaps.",
            },
            "reverse_validation_summary": {
                "status": "FAIL",
                "coverage_percent": 66.67,
                "mapped_required_rules": 2,
                "required_rules": 3,
                "unmapped_required_rules": 1,
                "note": "Some required targets have no source mapping path in the spec and should be mapped before sign-off.",
            },
            "mapping_completeness": {
                "status": "WARN",
                "basis": "spec_projection",
                "score_percent": 66.67,
                "satisfied_mandatory_rules": 2,
                "total_mandatory_rules": 3,
                "note": "Score is based on required spec rules that include source mapping paths.",
            },
            "warnings": [],
            "errors": [],
            "valid": True,
        }

    def _stub_payload_bridge(*_args, **_kwargs):
        raise AssertionError("payload bridge path should not run in spec_coverage mode")

    monkeypatch.setattr(main, "parse_args", _stub_parse_args)
    monkeypatch.setattr(main, "validate_spec_coverage", _stub_validate_spec_coverage)
    monkeypatch.setattr(main, "validate_mapping_from_payload_bytes", _stub_payload_bridge)
    monkeypatch.setattr(main, "write_report", lambda result, report: Path(report))

    exit_code = main.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["spec"] == str(spec_path)
    assert "Rule-gap summary:" in output
    assert "Next action:" in output
    assert "Reverse validation:" in output
    assert "Completeness:" in output


def test_main_batch_manifest_runs_all_pairs(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "spec.xlsx"
    manifest_path = tmp_path / "batch_manifest.json"
    report_path = tmp_path / "batch_report.json"
    input_a = tmp_path / "input_a.xml"
    output_a = tmp_path / "output_a.xml"
    input_b = tmp_path / "input_b.xml"
    output_b = tmp_path / "output_b.xml"

    spec_path.write_bytes(b"fake spec")
    input_a.write_text("<root/>", encoding="utf-8")
    output_a.write_text("<root/>", encoding="utf-8")
    input_b.write_text("<root/>", encoding="utf-8")
    output_b.write_text("<root/>", encoding="utf-8")
    manifest_path.write_text(
        "["
        f"{{\"id\":\"pairA\",\"input\":\"{input_a.as_posix()}\",\"output\":\"{output_a.as_posix()}\"}},"
        f"{{\"id\":\"pairB\",\"input\":\"{input_b.as_posix()}\",\"output\":\"{output_b.as_posix()}\"}}"
        "]",
        encoding="utf-8",
    )

    calls = []

    def _stub_parse_args():
        class _Args:
            spec = str(spec_path)
            input = "unused_input.xml"
            output = "unused_output.xml"
            report = str(report_path)
            mode = "strict"
            batch_manifest = str(manifest_path)
        return _Args()

    def _stub_validate(spec, input_payload, input_filename, output_payload, output_filename, validation_mode="strict"):
        calls.append((spec, input_filename, output_filename, validation_mode))
        status = "PASS" if "a" in input_filename else "FAIL"
        return {
            "summary": {"status": status, "parser_status": "clean", "parser_confidence": "high"},
            "human_summary": {"headline": "Validation completed", "issue_breakdown": [], "what_to_fix_first": []},
            "warnings": [],
            "errors": [] if status == "PASS" else ["error"],
            "error_count": 0 if status == "PASS" else 1,
            "valid": status == "PASS",
            "rule_gap_summary": {},
            "mapping_completeness": {},
            "reverse_validation_summary": {},
        }

    monkeypatch.setattr(main, "parse_args", _stub_parse_args)
    monkeypatch.setattr(main, "validate_mapping_from_payload_bytes", _stub_validate)
    monkeypatch.setattr(main, "write_report", lambda result, report: Path(report))

    exit_code = main.main()
    output = capsys.readouterr().out

    assert len(calls) == 2
    assert exit_code == 1
    assert "Batch validation completed" in output


def test_main_spec_diff_mode_and_excel_export(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "base.xlsx"
    compare_path = tmp_path / "next.xlsx"
    report_path = tmp_path / "spec_diff_report.json"
    xlsx_path = tmp_path / "spec_diff_report.xlsx"
    spec_path.write_bytes(b"base")
    compare_path.write_bytes(b"next")

    captured = {}

    def _stub_parse_args():
        class _Args:
            spec = str(spec_path)
            spec_compare = str(compare_path)
            input = "unused_input.xml"
            output = "unused_output.xml"
            report = str(report_path)
            report_xlsx = str(xlsx_path)
            mode = "strict"
            batch_manifest = ""
            generate_payload = ""
            generated_prefix = str(tmp_path / "generated_payload")
        return _Args()

    def _stub_diff_specs(base_spec, compare_spec):
        captured["base"] = base_spec
        captured["compare"] = compare_spec
        return {
            "summary": {"status": "PASS", "parser_status": "clean", "parser_confidence": "high"},
            "human_summary": {"headline": "Spec diff done", "issue_breakdown": [], "what_to_fix_first": []},
            "warnings": [],
            "errors": [],
            "valid": True,
        }

    monkeypatch.setattr(main, "parse_args", _stub_parse_args)
    monkeypatch.setattr(main, "diff_specs", _stub_diff_specs)
    monkeypatch.setattr(main, "write_report", lambda result, report: Path(report))
    monkeypatch.setattr(main, "write_excel_report", lambda result, out: Path(out))

    exit_code = main.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["base"] == str(spec_path)
    assert captured["compare"] == str(compare_path)
    assert "Excel report written to" in output


def test_main_generate_payload_mode_writes_generated_files(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "spec.xlsx"
    report_path = tmp_path / "payload_report.json"
    generated_prefix = tmp_path / "payload_out"
    spec_path.write_bytes(b"spec")

    captured = {}

    generated_prefix_str = str(generated_prefix)

    def _stub_parse_args():
        class _Args:
            spec = str(spec_path)
            spec_compare = ""
            input = "unused_input.xml"
            output = "unused_output.xml"
            report = str(report_path)
            report_xlsx = ""
            mode = "strict"
            batch_manifest = ""
            generate_payload = "template"
            generated_prefix = generated_prefix_str
        return _Args()

    def _stub_generate_payload_bundle(spec, mode):
        captured["spec"] = spec
        captured["mode"] = mode
        return {
            "summary": {"status": "PASS", "parser_status": "clean", "parser_confidence": "high"},
            "human_summary": {"headline": "Generated", "issue_breakdown": [], "what_to_fix_first": []},
            "warnings": [],
            "errors": [],
            "valid": True,
            "generated_payloads": {"input": {"a": 1}, "output": {"b": 2}},
        }

    def _stub_write_generated_payload_files(result, prefix):
        captured["prefix"] = prefix
        return {
            "input": Path(f"{prefix}_input.json"),
            "output": Path(f"{prefix}_output.json"),
        }

    monkeypatch.setattr(main, "parse_args", _stub_parse_args)
    monkeypatch.setattr(main, "generate_payload_bundle", _stub_generate_payload_bundle)
    monkeypatch.setattr(main, "write_generated_payload_files", _stub_write_generated_payload_files)
    monkeypatch.setattr(main, "write_report", lambda result, report: Path(report))

    exit_code = main.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["spec"] == str(spec_path)
    assert captured["mode"] == "template"
    assert captured["prefix"] == str(generated_prefix)
    assert "Generated payload files:" in output
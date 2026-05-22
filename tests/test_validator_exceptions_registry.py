from pathlib import Path

from scripts.check_validator_exceptions import validate_registry


def test_validator_exceptions_registry_current_file_is_valid():
    registry_path = Path(__file__).resolve().parents[1] / "rules" / "validator_exceptions.json"
    errors = validate_registry(registry_path)
    assert errors == []

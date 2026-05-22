import argparse
import json
from datetime import date
from pathlib import Path


def _parse_iso_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def validate_registry(path: Path, today: date | None = None) -> list[str]:
    if today is None:
        today = date.today()

    errors: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ["Registry root must be a JSON object"]

    entries = payload.get("entries")
    if not isinstance(entries, list):
        return ["Registry must include an 'entries' array"]

    seen_ids: set[str] = set()
    for idx, entry in enumerate(entries):
        prefix = f"entries[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue

        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            errors.append(f"{prefix}.id is required")
        elif entry_id in seen_ids:
            errors.append(f"{prefix}.id '{entry_id}' is duplicated")
        else:
            seen_ids.add(entry_id)

        status = str(entry.get("status") or "active").strip().lower()
        if status not in {"active", "inactive"}:
            errors.append(f"{prefix}.status must be 'active' or 'inactive'")

        required_fields = ["kind", "target_xpath", "owner", "reason", "added_on", "review_by"]
        for field in required_fields:
            value = str(entry.get(field) or "").strip()
            if not value:
                errors.append(f"{prefix}.{field} is required")

        for list_field in ["expected_values", "allowed_found_values"]:
            values = entry.get(list_field)
            if not isinstance(values, list) or not values:
                errors.append(f"{prefix}.{list_field} must be a non-empty array")

        row = entry.get("row")
        if not isinstance(row, int) or row <= 0:
            errors.append(f"{prefix}.row must be a positive integer")

        added_on = _parse_iso_date(str(entry.get("added_on") or ""))
        review_by = _parse_iso_date(str(entry.get("review_by") or ""))
        if added_on is None:
            errors.append(f"{prefix}.added_on must be ISO date YYYY-MM-DD")
        if review_by is None:
            errors.append(f"{prefix}.review_by must be ISO date YYYY-MM-DD")
        if added_on is not None and review_by is not None and review_by < added_on:
            errors.append(f"{prefix}.review_by cannot be earlier than added_on")

        if status == "active" and review_by is not None and review_by < today:
            errors.append(f"{prefix}.review_by has expired for active exception")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rules/validator_exceptions.json governance constraints")
    parser.add_argument(
        "--path",
        default="rules/validator_exceptions.json",
        help="Path to validator exceptions registry",
    )
    args = parser.parse_args()

    registry_path = Path(args.path)
    issues = validate_registry(registry_path)
    if issues:
        print("Validator exception registry check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print(f"Validator exception registry check passed: {registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

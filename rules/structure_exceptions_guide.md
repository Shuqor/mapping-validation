# Structure Exceptions Guide (Non-Technical)

This guide is for mappers.
You do not need to change Python code.

Use file: `rules/structure_exceptions.json`

## When To Edit This File

Edit this file only when validation is correct for most cases, but one spec needs a known exception.

Examples:
- A branch is intentionally not present for this partner
- An extra node is intentionally present
- A specific extra attribute is intentionally present

## Quick Mental Model

- `ignore_required_paths`: "Do not fail if this required branch is missing"
- `allow_nodes`: "Do not fail if this extra node appears"
- `allow_attributes`: "Do not fail if this extra attribute appears"
- `ordered_sibling_groups`: "These child nodes must appear in this order"
- `choice_groups`: "Only one (or a limited number) of these options is allowed"

## Copy/Paste Template

```json
{
  "specs": {
    "YOUR_SPEC_FILE_NAME.xlsx": {
      "ignore_required_paths": [],
      "allow_nodes": [],
      "allow_attributes": [],
      "ordered_sibling_groups": [],
      "choice_groups": []
    }
  }
}
```

## Practical Examples

### 1) Ignore one missing branch for one spec

```json
{
  "specs": {
    "spec.xlsx": {
      "ignore_required_paths": ["/interchange"],
      "allow_nodes": [],
      "allow_attributes": [],
      "ordered_sibling_groups": [],
      "choice_groups": []
    }
  }
}
```

### 2) Allow one extra node

```json
{
  "specs": {
    "partner_spec.xlsx": {
      "ignore_required_paths": [],
      "allow_nodes": ["/status/debugInfo"],
      "allow_attributes": [],
      "ordered_sibling_groups": [],
      "choice_groups": []
    }
  }
}
```

### 3) Enforce one-of rule (choice)

```json
{
  "specs": {
    "partner_spec.xlsx": {
      "ignore_required_paths": [],
      "allow_nodes": [],
      "allow_attributes": [],
      "ordered_sibling_groups": [],
      "choice_groups": [
        {
          "parent_path": "/status/detail",
          "options": ["/status/detail/optionA", "/status/detail/optionB"],
          "min": 1,
          "max": 1
        }
      ]
    }
  }
}
```

## Important Notes

- Use exact spec filename as key (for example `spec.xlsx`).
- Paths should start with `/`.
- If JSON format is broken, validator safely falls back to built-in defaults.
- After editing, run validation again.

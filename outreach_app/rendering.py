from __future__ import annotations

import re
from string import Formatter
from typing import Any


FIELD_PATTERN = re.compile(r"{([^{}]+)}")


class TemplateError(ValueError):
    pass


def normalize_template(template: str) -> str:
    """Convert human placeholders like {Club Name} to safe Formatter fields."""
    return FIELD_PATTERN.sub(lambda match: "{" + _field_key(match.group(1)) + "}", template)


def required_fields(*templates: str) -> set[str]:
    fields: set[str] = set()
    formatter = Formatter()
    for template in templates:
        normalized = normalize_template(template)
        for _, field_name, _, _ in formatter.parse(normalized):
            if field_name:
                fields.add(field_name)
    return fields


def render(template: str, data: dict[str, Any]) -> str:
    normalized_data = {_field_key(key): value for key, value in data.items()}
    normalized_template = normalize_template(template)
    missing = sorted(required_fields(template) - normalized_data.keys())
    if missing:
        raise TemplateError(f"Missing template fields: {', '.join(missing)}")
    return normalized_template.format(**normalized_data)


def _field_key(value: str) -> str:
    key = re.sub(r"\W+", "_", value.strip()).strip("_")
    if not key:
        raise TemplateError("Template contains an empty field")
    return key

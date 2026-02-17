"""Convert nested Python dicts/lists to PHP bracket-notation query parameters.

Daktela's API uses PHP-style query parameters like:
    filter[0][field]=stage&filter[0][operator]=eq&filter[0][value]=OPEN

This module provides flatten_params() which converts a nested Python structure
into a flat dict suitable for passing as httpx query params.
"""

from typing import Any


def flatten_params(params: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict/list structure into PHP bracket-notation query params.

    Examples:
        >>> flatten_params({"skip": 0, "take": 50})
        {"skip": "0", "take": "50"}

        >>> flatten_params({"filter": [{"field": "stage", "operator": "eq", "value": "OPEN"}]})
        {"filter[0][field]": "stage", "filter[0][operator]": "eq", "filter[0][value]": "OPEN"}
    """
    result: dict[str, str] = {}

    for key, value in params.items():
        full_key = f"{prefix}[{key}]" if prefix else str(key)

        if isinstance(value, dict):
            result.update(flatten_params(value, prefix=full_key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                item_key = f"{full_key}[{i}]"
                if isinstance(item, dict):
                    result.update(flatten_params(item, prefix=item_key))
                else:
                    result[item_key] = str(item)
        elif value is not None:
            result[full_key] = str(value)

    return result


def build_filters(
    *,
    field_filters: list[tuple[str, str, str | list[str]]] | None = None,
    skip: int = 0,
    take: int = 50,
    sort: str | None = None,
    sort_dir: str = "desc",
    fields: list[str] | None = None,
) -> dict[str, str]:
    """Build flattened query params for a Daktela API request.

    Args:
        field_filters: List of (field, operator, value) tuples.
            Operators: eq, ne, gte, lte, gt, lt, like, in
            For 'in' operator, value should be a list of strings.
        skip: Number of records to skip (pagination offset).
        take: Number of records to return (max 1000).
        sort: Field name to sort by.
        sort_dir: Sort direction ('asc' or 'desc').
        fields: List of field names to return (for partial responses).
    """
    params: dict[str, Any] = {"skip": skip, "take": take}

    if field_filters:
        filters = []
        for field, operator, value in field_filters:
            # Daktela's 'like' is SQL LIKE — wrap in % for partial/contains matching
            if operator == "like" and isinstance(value, str) and "%" not in value:
                value = f"%{value}%"
            filters.append({"field": field, "operator": operator, "value": value})
        params["filter"] = filters

    if sort:
        params["sort"] = [{"field": sort, "dir": sort_dir}]

    if fields:
        params["fields"] = fields

    return flatten_params(params)

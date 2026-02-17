from mcp_daktela.filters import build_filters, flatten_params


class TestFlattenParams:
    def test_flat_dict(self):
        assert flatten_params({"skip": 0, "take": 50}) == {"skip": "0", "take": "50"}

    def test_nested_dict(self):
        result = flatten_params({"sort": {"edited": "desc"}})
        assert result == {"sort[edited]": "desc"}

    def test_list_of_dicts(self):
        result = flatten_params({
            "filter": [
                {"field": "stage", "operator": "eq", "value": "OPEN"},
            ]
        })
        assert result == {
            "filter[0][field]": "stage",
            "filter[0][operator]": "eq",
            "filter[0][value]": "OPEN",
        }

    def test_multiple_filters(self):
        result = flatten_params({
            "filter": [
                {"field": "stage", "operator": "eq", "value": "OPEN"},
                {"field": "edited", "operator": "gte", "value": "2024-01-01"},
            ]
        })
        assert result == {
            "filter[0][field]": "stage",
            "filter[0][operator]": "eq",
            "filter[0][value]": "OPEN",
            "filter[1][field]": "edited",
            "filter[1][operator]": "gte",
            "filter[1][value]": "2024-01-01",
        }

    def test_list_of_scalars(self):
        result = flatten_params({"fields": ["name", "title"]})
        assert result == {"fields[0]": "name", "fields[1]": "title"}

    def test_none_values_skipped(self):
        result = flatten_params({"skip": 0, "sort": None})
        assert result == {"skip": "0"}

    def test_empty_dict(self):
        assert flatten_params({}) == {}

    def test_deeply_nested(self):
        result = flatten_params({"a": {"b": {"c": "deep"}}})
        assert result == {"a[b][c]": "deep"}


class TestBuildFilters:
    def test_defaults(self):
        result = build_filters()
        assert result == {"skip": "0", "take": "50"}

    def test_with_field_filters(self):
        result = build_filters(field_filters=[("stage", "eq", "OPEN")])
        assert result["filter[0][field]"] == "stage"
        assert result["filter[0][operator]"] == "eq"
        assert result["filter[0][value]"] == "OPEN"
        assert result["skip"] == "0"
        assert result["take"] == "50"

    def test_with_sort(self):
        result = build_filters(sort="edited", sort_dir="asc")
        assert result["sort[0][field]"] == "edited"
        assert result["sort[0][dir]"] == "asc"

    def test_with_fields(self):
        result = build_filters(fields=["name", "title"])
        assert result["fields[0]"] == "name"
        assert result["fields[1]"] == "title"

    def test_pagination(self):
        result = build_filters(skip=100, take=25)
        assert result == {"skip": "100", "take": "25"}

    def test_like_operator_wraps_value_in_wildcards(self):
        result = build_filters(field_filters=[("title", "like", "Notino")])
        assert result["filter[0][operator]"] == "like"
        assert result["filter[0][value]"] == "%Notino%"

    def test_like_operator_does_not_double_wrap(self):
        result = build_filters(field_filters=[("title", "like", "%already%")])
        assert result["filter[0][value]"] == "%already%"

    def test_like_operator_partial_wildcard_left_unchanged(self):
        result = build_filters(field_filters=[("title", "like", "prefix%")])
        assert result["filter[0][value]"] == "prefix%"

    def test_in_operator_with_list_value(self):
        result = build_filters(field_filters=[("contact", "in", ["CT001", "CT002", "CT003"])])
        assert result["filter[0][field]"] == "contact"
        assert result["filter[0][operator]"] == "in"
        assert result["filter[0][value][0]"] == "CT001"
        assert result["filter[0][value][1]"] == "CT002"
        assert result["filter[0][value][2]"] == "CT003"

    def test_combined(self):
        result = build_filters(
            field_filters=[("category", "eq", "Sales")],
            skip=0,
            take=10,
            sort="created",
            sort_dir="desc",
        )
        assert result["filter[0][field]"] == "category"
        assert result["sort[0][field]"] == "created"
        assert result["sort[0][dir]"] == "desc"
        assert result["skip"] == "0"
        assert result["take"] == "10"

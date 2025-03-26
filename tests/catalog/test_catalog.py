import os
import json
import pytest
from unittest.mock import patch, mock_open
from envhero.catalog.catalog import load_catalog, filter_vars_by_tag, save_catalog, add_tags_to_present_vars
from envhero.catalog.from_env import exists_in_env

# Test data
SAMPLE_CATALOG = [
    {"name": "API_KEY", "has_default": False, "tags": ["api", "auth"]},
    {"name": "DEBUG", "has_default": True, "default_value": "False", "tags": ["__all__"]},
    {"name": "DATABASE_URL", "has_default": False, "tags": ["db", "api"]},
    {"name": "LOG_LEVEL", "has_default": True, "default_value": "INFO", "tags": []},
]


class TestLoadCatalog:
    def test_load_catalog_successfully(self):
        with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_CATALOG))):
            result = load_catalog("test_catalog.json")
            assert result == SAMPLE_CATALOG

    def test_load_catalog_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError()), pytest.raises(SystemExit) as exc_info:
            load_catalog("nonexistent.json")
        assert "not found" in str(exc_info.value)

    def test_load_catalog_invalid_json(self):
        with patch("builtins.open", mock_open(read_data="invalid json")), pytest.raises(SystemExit) as exc_info:
            load_catalog("invalid.json")
        assert "invalid JSON" in str(exc_info.value)


class TestFilterVarsByTag:
    def test_filter_with_no_tags(self):
        result = filter_vars_by_tag(SAMPLE_CATALOG, [])
        assert result == SAMPLE_CATALOG

    def test_filter_with_single_tag(self):
        result = filter_vars_by_tag(SAMPLE_CATALOG, ["api"])
        assert len(result) == 3  # API_KEY, DEBUG (has __all__), DATABASE_URL
        assert result[0]["name"] == "API_KEY"
        assert result[1]["name"] == "DEBUG"
        assert result[2]["name"] == "DATABASE_URL"

    def test_filter_with_multiple_tags(self):
        result = filter_vars_by_tag(SAMPLE_CATALOG, ["auth", "db"])
        assert len(result) == 3  # API_KEY, DEBUG (has __all__), DATABASE_URL

    def test_filter_no_matches(self):
        result = filter_vars_by_tag(SAMPLE_CATALOG, ["nonexistent"])
        assert len(result) == 1  # Only DEBUG with __all__ tag
        assert result[0]["name"] == "DEBUG"


class TestSaveCatalog:
    def test_save_catalog_successfully(self):
        with patch("builtins.open", mock_open()) as m, patch("json.dump") as mock_json_dump, patch(
            "builtins.print"
        ) as mock_print:
            save_catalog(SAMPLE_CATALOG, "output.json")

            m.assert_called_once_with("output.json", "w", encoding="utf-8")
            mock_json_dump.assert_called_once()
            mock_print.assert_called_once_with("Successfully saved catalog with 4 variables to 'output.json'")

    def test_save_catalog_io_error(self):
        with patch("builtins.open", side_effect=IOError("Permission denied")), pytest.raises(SystemExit) as exc_info:
            save_catalog(SAMPLE_CATALOG, "/invalid/path/output.json")
        assert "Failed to write catalog" in str(exc_info.value)
        assert "Permission denied" in str(exc_info.value)


class TestAddTagsToPresentVars:
    def test_add_tags_no_tags_provided(self):
        result = add_tags_to_present_vars(SAMPLE_CATALOG, [], environ_exists=exists_in_env)
        assert result == SAMPLE_CATALOG

    @patch.dict(os.environ, {"API_KEY": "test-key", "LOG_LEVEL": "DEBUG"})
    def test_add_tags_to_present_vars(self):
        result = add_tags_to_present_vars(SAMPLE_CATALOG, ["production"], environ_exists=exists_in_env)

        # API_KEY should have production tag added
        api_key_var = next(var for var in result if var["name"] == "API_KEY")
        assert "production" in api_key_var["tags"]

        # LOG_LEVEL should have production tag added and be the first tag
        log_level_var = next(var for var in result if var["name"] == "LOG_LEVEL")
        assert "production" in log_level_var["tags"]

        # DATABASE_URL shouldn't have production tag since it's not in environment
        db_url_var = next(var for var in result if var["name"] == "DATABASE_URL")
        assert "production" not in db_url_var["tags"]

    @patch.dict(os.environ, {"API_KEY": "test-key"})
    def test_add_tags_no_duplicates(self):
        # Add a tag that already exists
        catalog_copy = json.loads(json.dumps(SAMPLE_CATALOG))
        result = add_tags_to_present_vars(catalog_copy, ["api"], environ_exists=exists_in_env)

        # API_KEY should have api tag only once
        api_key_var = next(var for var in result if var["name"] == "API_KEY")
        assert api_key_var["tags"].count("api") == 1

    @patch.dict(os.environ, {"NEW_VAR": "value"})
    def test_add_tags_var_not_in_catalog(self):
        # This tests that the function doesn't throw errors when var in env
        # but not in catalog
        result = add_tags_to_present_vars(SAMPLE_CATALOG, ["production"], environ_exists=exists_in_env)
        assert result == SAMPLE_CATALOG  # No changes to catalog

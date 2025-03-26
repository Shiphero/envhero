import json
from unittest.mock import patch, mock_open

from app.app import create_env_var_catalogue, update_env_var_catalogue, check_env_vars, print_structured, main


class TestCreateEnvVarCatalogue:
    @patch("catalog.scan_codebase")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_create_env_var_catalogue(self, mock_json_dump, mock_file, mock_scan_codebase):
        # Mock scan_codebase to return some test data
        mock_catalog = [
            {
                "name": "VAR1",
                "has_default": True,
                "default_value": "default",
                "locations": [{"file": "test.py", "line": 10}],
            }
        ]
        mock_scan_codebase.return_value = (mock_catalog, 1)

        # Call the function
        create_env_var_catalogue(
            output_file="catalog.json",
            exclude_dirs=["venv", "__pycache__", ".local", ".venv"],
            exclude_patterns=["*.pyc"],
            no_auto_tag=False,
        )

        # Verify scan_codebase was called with the correct arguments
        mock_scan_codebase.assert_called_once_with(".", ["venv", "__pycache__", ".local", ".venv"], ["*.pyc"], False)

        # Verify the file was opened for writing
        mock_file.assert_called_once_with("catalog.json", "w", encoding="utf-8")

        # Verify json.dump was called with the list of variables
        mock_json_dump.assert_called_once()
        # Check that first argument to json.dump was the converted catalog
        args, _ = mock_json_dump.call_args
        assert isinstance(args[0], list)
        assert len(args[0]) == 1
        assert args[0][0]["name"] == "VAR1"


class TestUpdateEnvVarCatalogue:
    @patch("catalog.scan_codebase")
    @patch("catalog.load_catalog")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    @patch("os.path.exists")
    def test_update_env_var_catalogue(
        self, mock_exists, mock_json_dump, mock_file, mock_load_catalog, mock_scan_codebase
    ):
        # Mock load_catalog to return existing catalog
        existing_catalog = [
            {"name": "EXISTING_VAR", "has_default": True, "default_value": "old_default", "tags": ["api"]}
        ]
        mock_load_catalog.return_value = existing_catalog
        mock_exists.return_value = True

        # Mock scan_codebase to return new findings
        new_catalog = [
            {
                "name": "EXISTING_VAR",
                "has_default": True,
                "default_value": "old_default",
                "locations": [{"file": "old.py", "line": 5}],
            },
            {
                "name": "NEW_VAR",
                "has_default": True,
                "default_value": "new_default",
                "locations": [{"file": "new.py", "line": 15}],
            },
        ]
        mock_scan_codebase.return_value = (new_catalog, 2)

        # Call the function
        update_env_var_catalogue(
            output_file="updated_catalog.json", exclude_dirs=["venv"], exclude_patterns=[], no_auto_tag=True
        )

        # Verify correct methods were called
        mock_scan_codebase.assert_called_once()
        mock_load_catalog.assert_called_once_with("updated_catalog.json")
        mock_file.assert_called_once_with("updated_catalog.json", "wt", encoding="utf-8")
        mock_json_dump.assert_called_once()

        # Check that merged catalog was passed to json.dump
        args, _ = mock_json_dump.call_args
        saved_catalog = args[0]
        assert isinstance(saved_catalog, list)
        assert len(saved_catalog) == 2

        # Check that both variables are in the result
        var_names = [var["name"] for var in saved_catalog]
        assert "EXISTING_VAR" in var_names
        assert "NEW_VAR" in var_names


class TestCheckEnvVars:
    @patch("catalog.scan_codebase")
    @patch("builtins.open")
    @patch("json.load")
    @patch("builtins.print")
    @patch("app.print_structured")
    def test_check_env_vars_missing_vars(
        self, mock_print_structured, mock_print, mock_json_load, mock_open, mock_scan_codebase
    ):
        # Mock catalog loading
        mock_json_load.return_value = [{"name": "KNOWN_VAR", "has_default": True, "default_value": "default"}]

        # Mock file existence
        with patch("os.path.exists", return_value=True):
            # Mock scan_codebase to return findings including one that's not in the catalog
            new_findings = [
                {
                    "name": "KNOWN_VAR",
                    "has_default": True,
                    "default_value": "default",
                    "locations": [{"file": "known.py", "line": 10}],
                },
                {
                    "name": "UNKNOWN_VAR",
                    "has_default": True,
                    "default_value": "value",
                    "locations": [{"file": "unknown.py", "line": 20}],
                },
            ]
            mock_scan_codebase.return_value = (new_findings, 2)

            # Call the function with structured output
            check_env_vars(
                output_file="catalog.json", exclude_dirs=["venv"], exclude_patterns=[], structured_output=True
            )

            # Verify print_structured was called with the uncataloged variable
            mock_print_structured.assert_called_once()
            args, _ = mock_print_structured.call_args
            assert len(args[0]) == 1
            assert args[0][0]["name"] == "UNKNOWN_VAR"

    def test_check_env_vars_missing_catalog(self):
        with patch("os.path.exists", return_value=False), patch("builtins.print") as mock_print:
            check_env_vars(output_file="nonexistent.json")

            # Should print error about missing catalog
            mock_print.assert_called_once_with("Catalog file nonexistent.json not found")


class TestMain:
    @patch("app.create_env_var_catalogue")
    def test_main_create(self, mock_create):
        with patch("sys.argv", ["app.py", "create", "-o", "test.json"]):
            main()
            mock_create.assert_called_once_with(
                output_file="test.json",
                exclude_dirs=[".venv", "__pycache__", ".git"],
                exclude_patterns=[],
                no_auto_tag=False,
            )

    @patch("app.update_env_var_catalogue")
    def test_main_update(self, mock_update):
        with patch("sys.argv", ["app.py", "update", "-o", "test.json"]):
            main()
            mock_update.assert_called_once_with(
                output_file="test.json",
                exclude_dirs=[".venv", "__pycache__", ".git"],
                exclude_patterns=[],
                no_auto_tag=False,
            )

    @patch("app.check_env_vars")
    def test_main_check(self, mock_check):
        with patch("sys.argv", ["app.py", "check", "-c", "test.json", "--structured-output"]):
            main()
            mock_check.assert_called_once_with(
                output_file="test.json",
                exclude_dirs=[".venv", "__pycache__", ".git"],
                exclude_patterns=[],
                structured_output=True,
                no_auto_tag=False,
            )

    @patch("catalog.load_catalog")
    @patch("catalog.filter_vars_by_tag")
    @patch("environment.check_environment_variables")
    @patch("sys.exit")
    def test_main_verify(self, mock_exit, mock_check_env, mock_filter, mock_load):
        catalog_data = [{"name": "API_VAR", "tags": ["api"]}, {"name": "DB_VAR", "tags": ["db"]}]
        mock_load.return_value = catalog_data
        mock_filter.return_value = [{"name": "API_VAR", "tags": ["api"]}]
        mock_check_env.return_value = True

        with patch("sys.argv", ["app.py", "verify", "-c", "test.json", "-t", "api"]):
            main()

            mock_load.assert_called_once_with("test.json")
            mock_filter.assert_called_once_with(catalog_data, ["api"])
            mock_check_env.assert_called_once_with(
                catalog_vars=[{"name": "API_VAR", "tags": ["api"]}], warning_as_error=False
            )
            mock_exit.assert_called_once_with(0)  # All checks passed

    @patch("catalog.load_catalog")
    @patch("catalog.add_tags_to_present_vars")
    @patch("catalog.save_catalog")
    def test_main_tags_from_env(self, mock_save, mock_add_tags, mock_load):
        catalog_data = [{"name": "TEST_VAR1", "tags": []}, {"name": "TEST_VAR2", "tags": ["existing"]}]
        mock_load.return_value = catalog_data

        updated_catalog = [{"name": "TEST_VAR1", "tags": ["prod"]}, {"name": "TEST_VAR2", "tags": ["existing", "prod"]}]
        mock_add_tags.return_value = updated_catalog

        with patch("sys.argv", ["app.py", "tags_from_env", "-c", "test.json", "-t", "prod"]):
            main()

            mock_load.assert_called_once_with("test.json")
            mock_add_tags.assert_called_once_with(catalog_data, ["prod"])
            mock_save.assert_called_once_with("test.json")


class TestPrintStructured:
    @patch("builtins.print")
    def test_print_structured(self, mock_print):
        test_data = [
            {"name": "VAR1", "default_value": "value1", "tags": ["api"]},
            {"name": "VAR2", "default_value": None, "tags": ["db"]},
        ]

        print_structured(test_data)

        # Verify json.dumps was called through print
        mock_print.assert_called_once()
        args, _ = mock_print.call_args
        printed_json = args[0]

        # Parse the printed JSON to verify it's valid
        parsed = json.loads(printed_json)
        assert isinstance(parsed, dict)
        assert "VAR1" in parsed
        assert "VAR2" in parsed

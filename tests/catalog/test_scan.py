import sys
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from catalog.scan import (
    find_base_tag,
    find_package_name,
    scan_codebase
)

class TestFindBaseTag:
    def test_simple_path(self):
        assert find_base_tag(Path("api/client.py")) == "api"

    def test_nested_path(self):
        assert find_base_tag(Path("services/api/client.py")) == "services"

    def test_src_path(self):
        assert find_base_tag(Path("src/api/client.py")) == "api"

    def test_current_dir(self):
        assert find_base_tag(Path("file.py")) == ""

    def test_empty_path(self):
        assert find_base_tag(Path(".")) == ""

class TestFindPackageName:
    def test_simple_file(self):
        assert find_package_name(Path("api/client.py")) == "api"

    def test_src_structure(self):
        assert find_package_name(Path("src/mypackage/module.py")) == "mypackage"

    def test_lib_structure(self):
        assert find_package_name(Path("lib/utils/helper.py")) == "utils"

    def test_packages_structure(self):
        assert find_package_name(Path("packages/auth/login.py")) == "auth"

    def test_root_file(self):
        assert find_package_name(Path("setup.py")) == ""

class TestScanCodebase:
    @pytest.fixture
    def mock_file_system(self):
        """Create a mock file system structure for testing"""
        with patch('os.walk') as mock_walk:
            # Simulate directory structure
            mock_walk.return_value = [
                ('./api', [], ['client.py', 'utils.py']),
                ('./db', [], ['models.py']),
                ('./tests', [], ['test_api.py']),
                ('./venv', [], ['activate.py']),
            ]
            yield mock_walk

    @pytest.fixture
    def mock_env_var_content(self):
        """Mock Python file content with environment variables"""
        api_client = """
import os
def get_api_url():
    return os.environ.get('API_URL', 'https://api.example.com')
    
def get_timeout():
    return int(os.environ.get('API_TIMEOUT', '30'))
"""
        api_utils = """
import os
from typing import Optional

DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
"""
        db_models = """
import os
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is required")
"""
        test_file = """
import os
# Test file should be ignored
TEST_API_KEY = os.environ.get('TEST_API_KEY', 'fake-key')
"""

        def mock_open_impl(file_path, *args, **kwargs):
            content = ""
            str_path = str(file_path)
            if "client.py" in str_path:
                content = api_client
            elif "utils.py" in str_path:
                content = api_utils
            elif "models.py" in str_path:
                content = db_models
            elif "test_api.py" in str_path:
                content = test_file

            file_mock = mock_open(read_data=content).return_value
            return file_mock

        return mock_open_impl

    def test_scan_codebase_basic(self, mock_file_system, mock_env_var_content):
        with patch('builtins.open', side_effect=mock_env_var_content):
            with patch('ast.parse') as mock_parse:
                # Configure our visitor behavior for each file
                visitor_instances = []

                # Mock the visitor for api/client.py
                api_client_visitor = MagicMock()
                api_client_visitor.env_vars = [
                    {"name": "API_URL", "has_default": True, "default_value": "https://api.example.com",
                     "lineno": 3, "inferred_type": "str"},
                    {"name": "API_TIMEOUT", "has_default": True, "default_value": "30",
                     "lineno": 6, "inferred_type": "int"}
                ]
                visitor_instances.append(api_client_visitor)

                # Mock the visitor for api/utils.py
                api_utils_visitor = MagicMock()
                api_utils_visitor.env_vars = [
                    {"name": "DEBUG", "has_default": True, "default_value": "False",
                     "lineno": 4, "inferred_type": "bool"}
                ]
                visitor_instances.append(api_utils_visitor)

                # Mock the visitor for db/models.py
                db_models_visitor = MagicMock()
                db_models_visitor.env_vars = [
                    {"name": "DATABASE_URL", "has_default": False, "default_value": None,
                     "lineno": 2, "inferred_type": "str"}
                ]
                visitor_instances.append(db_models_visitor)

                # Configure the mock to return our pre-configured visitors
                with patch('catalog.scan.EnvVarVisitor') as mock_visitor_class:
                    mock_visitor_class.side_effect = lambda: visitor_instances.pop(0)

                    # Run the scan
                    catalog, total = scan_codebase(
                        base_dir=".",
                        exclude_dirs=["venv", "tests"],
                        exclude_patterns=["test_"],
                        no_auto_tag=False
                    )

                    # Verify the results
                    assert total == 4, "Should have found 4 environment variables"
                    assert len(catalog) == 4, "Should have 4 unique environment variables in catalog"

                    # Check API_URL details
                    api_url_key = f"API_URL_https://api.example.com"
                    catalog_idx = -1
                    for idx, item in enumerate(catalog):
                        if f"{item['name']}_{item['default_value']}" == api_url_key:
                            catalog_idx = idx
                            break

                    assert catalog_idx >= 0
                    assert catalog[catalog_idx]["name"] == "API_URL"
                    assert catalog[catalog_idx]["has_default"] == True
                    assert catalog[catalog_idx]["default_value"] == "https://api.example.com"
                    assert catalog[catalog_idx]["inferred_type"] == "str"
                    assert "api" in catalog[catalog_idx]["tags"]
                    assert len(catalog[catalog_idx]["locations"]) == 1

                    # Check DATABASE_URL details
                    db_url_key = f"DATABASE_URL_None"
                    catalog_idx = -1
                    for idx, item in enumerate(catalog):
                        if f"{item['name']}_{item['default_value']}" == db_url_key:
                            catalog_idx = idx
                            break
                    assert catalog_idx >= 0
                    assert catalog[catalog_idx]["name"] == "DATABASE_URL"
                    assert catalog[catalog_idx]["has_default"] == False
                    assert "db" in catalog[catalog_idx]["tags"]

    def test_scan_codebase_with_auto_tag_disabled(self, mock_file_system, mock_env_var_content):
        with patch('builtins.open', side_effect=mock_env_var_content):
            with patch('ast.parse'), \
                 patch('catalog.scan.EnvVarVisitor') as mock_visitor_class:

                # Create a mock visitor with a single env var
                mock_visitor = MagicMock()
                mock_visitor.env_vars = [
                    {"name": "TEST_VAR", "has_default": True, "default_value": "test",
                     "lineno": 10, "inferred_type": "str"}
                ]
                mock_visitor_class.return_value = mock_visitor

                # Run the scan with no_auto_tag=True
                catalog, total = scan_codebase(
                    base_dir=".",
                    exclude_dirs=["venv"],
                    exclude_patterns=[],
                    no_auto_tag=True
                )

                # Since we mock the whole visitor, we only have one variable
                assert len(catalog) == 1
                # The tags should be an empty list after conversion from None
                assert catalog[0]["tags"] == []

    def test_scan_codebase_error_handling(self, mock_file_system):
        with patch('builtins.open', side_effect=IOError("File read error")), \
             patch('builtins.print') as mock_print, \
             pytest.raises(IOError):

            scan_codebase(
                base_dir=".",
                exclude_dirs=[],
                exclude_patterns=[],
                no_auto_tag=False
            )

            # Check error was reported to stderr
            mock_print.assert_called_once()
            args, kwargs = mock_print.call_args
            assert "Error processing" in args[0]
            assert kwargs.get('file') == sys.stderr

    def test_scan_codebase_exclude_patterns(self, mock_file_system, mock_env_var_content):
        with patch('builtins.open', side_effect=mock_env_var_content):
            with patch('ast.parse'), \
                 patch('catalog.scan.EnvVarVisitor') as mock_visitor_class:

                # Mock visitor instances for each file
                mock_visitor = MagicMock()
                mock_visitor.env_vars = [{"name": "SOME_VAR", "has_default": False, "default_value": None,
                                         "lineno": 1, "inferred_type": "str"}]
                mock_visitor_class.return_value = mock_visitor

                # Run scan with pattern that excludes utils.py
                catalog, total = scan_codebase(
                    base_dir=".",
                    exclude_dirs=["venv"],
                    exclude_patterns=["utils.py"],
                    no_auto_tag=False
                )

                # Calculate how many times the visitor was instantiated (how many files were processed)
                # It should be 3 files - utils.py
                assert mock_visitor_class.call_count == 3
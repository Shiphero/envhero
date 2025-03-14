import os
import pytest
from unittest.mock import patch

from environment.verify import (
    must_pass_check,
    EnvironmentVariableError,
    RequiredVariableMissingError,
    DefaultUsedAsError
)

# Test data - mock environment variables catalog
SAMPLE_CATALOG = [
    {
        "name": "DATABASE_URL",
        "has_default": False,
        "default_value": None,
        "tags": ["db", "api"]
    },
    {
        "name": "API_KEY",
        "has_default": True,
        "default_value": "dev-key-123",
        "tags": ["api", "auth"]
    },
    {
        "name": "DEBUG",
        "has_default": True,
        "default_value": "False",
        "tags": ["__all__"]
    },
    {
        "name": "LOG_LEVEL",
        "has_default": True,
        "default_value": "INFO",
        "tags": []
    },
]

class TestMustPassCheck:
    def test_all_required_vars_present(self):
        """Test when all required variables are present in the environment"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@localhost/db"}):
            # This should not raise any exceptions
            must_pass_check(SAMPLE_CATALOG, warning_as_error=False)

    def test_missing_required_var(self):
        """Test when a required variable is missing"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RequiredVariableMissingError) as exc_info:
                must_pass_check(SAMPLE_CATALOG, warning_as_error=False)

            # Verify the exception contains the correct variable name
            assert exc_info.value.var_name == "DATABASE_URL"
            assert "Required environment variable 'DATABASE_URL' is missing" in str(exc_info.value)

    def test_default_used_not_as_error(self):
        """Test when default values are used but warnings are not treated as errors"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://localhost/db"}):
            # Should not raise exceptions, just use defaults for API_KEY, DEBUG, and LOG_LEVEL
            must_pass_check(SAMPLE_CATALOG, warning_as_error=False)

    def test_default_used_as_error(self):
        """Test when default values are used and warnings are treated as errors"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://localhost/db"}):
            with pytest.raises(DefaultUsedAsError) as exc_info:
                must_pass_check(SAMPLE_CATALOG, warning_as_error=True)

            # First default value found (likely API_KEY) should trigger the error
            assert exc_info.value.var_name in ["API_KEY", "DEBUG", "LOG_LEVEL"]
            assert exc_info.value.default_value is not None
            assert "Environment variable 'API_KEY' is missing and using default 'dev-key-123', but warnings are treated as errors" in str(exc_info.value)

    def test_partial_environment(self):
        """Test with partial environment setup"""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgres://localhost/db",
            "API_KEY": "production-key",
            # DEBUG and LOG_LEVEL not set
        }):
            # Should not raise exceptions if warnings not treated as errors
            must_pass_check(SAMPLE_CATALOG, warning_as_error=False)

            # Should raise exception if warnings treated as errors
            with pytest.raises(DefaultUsedAsError):
                must_pass_check(SAMPLE_CATALOG, warning_as_error=True)

    def test_empty_catalog(self):
        """Test with empty catalog"""
        # Should not raise exceptions regardless of environment state
        must_pass_check([], warning_as_error=True)
        must_pass_check([], warning_as_error=False)

    def test_catalog_without_required_vars(self):
        """Test catalog with only optional variables"""
        optional_vars = [var for var in SAMPLE_CATALOG if var["has_default"]]

        with patch.dict(os.environ, {}):
            # Should not raise exceptions if warnings not treated as errors
            must_pass_check(optional_vars, warning_as_error=False)

            # Should raise exception if warnings treated as errors
            with pytest.raises(DefaultUsedAsError):
                must_pass_check(optional_vars, warning_as_error=True)

    def test_error_inheritance(self):
        """Test the inheritance hierarchy of custom exceptions"""
        assert issubclass(RequiredVariableMissingError, EnvironmentVariableError)
        assert issubclass(DefaultUsedAsError, EnvironmentVariableError)

        # Create instances to verify proper initialization
        required_error = RequiredVariableMissingError("TEST_VAR")
        default_error = DefaultUsedAsError("DEBUG_MODE", "false")

        assert required_error.var_name == "TEST_VAR"
        assert default_error.var_name == "DEBUG_MODE"
        assert default_error.default_value == "false"
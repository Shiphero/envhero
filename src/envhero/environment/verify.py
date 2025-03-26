#!/usr/bin/env python3
from typing import Any, Callable, Dict, List

SEPARATOR = "-" * 80


def print_var_status_formatted(
    as_error: bool, as_warning: bool, is_present: bool, idx: int, catalog_len: int, var: Dict[str, Any]
):
    var_name = var["name"]
    has_default = var.get("has_default", False)
    default_value = var.get("default_value")

    print(f"[{idx}/{catalog_len}] {var_name}")
    print(f"  Tags:      {', '.join(var.get('tags', ['unknown']))}")
    print(f"  Used in:       {', '.join(var.get('packages', ['unknown']))}")
    print(f"  Has default:   {has_default}")

    if has_default:
        print(f"  Default value: {default_value}")
    if is_present:
        print("  Status:        ✓ SET")
    elif as_error:  # error first, something can be an error and a warning given the right flag combo
        print("  Status:        ✗ ERROR - Required variable not set")
    elif as_warning:
        print(f"  Status:        ⚠ WARNING - Not set, using default: {default_value}")
    if var.get("locations"):
        locations = var.get("locations")[:3]
    # Display first few usage locations
    if var.get("locations"):
        locations = var.get("locations")[:3]
        if len(locations) > 0:
            print("  Referenced in:")
            for loc in locations:
                print(f"    • {loc['file']}:{loc['line']}")

            if len(var.get("locations", [])) > 3:
                print(f"    • ... and {len(var.get('locations', [])) - 3} more locations")


def check_individual_variable(
    idx: int, var: Dict, catalog_len: int, warning_as_error: bool, environ_exists: Callable[[str], bool]
):
    """Performs the variable sanity checking for the given var

    Also prints some extra information if possible
    """
    is_error = False
    is_warning = False
    var_name = var["name"]
    has_default = var.get("has_default", False)
    is_present = environ_exists(var_name)
    if is_present:
        return is_error, is_warning
    if has_default:
        is_warning = True
        if warning_as_error:
            is_error = True
    else:
        is_error = True

    return is_error, is_warning


def check_environment_variables(
    catalog_vars: List[Dict[str, Any]], warning_as_error: bool, environ_exists: Callable[[str], bool]
) -> bool:
    """Check if environment variables are set.

    Returns True if check passes, False otherwise, human-readable information is printed
    """
    all_passed = True
    errors = 0
    warnings = 0

    print(f"\nChecking {len(catalog_vars)} environment variables:")
    print(SEPARATOR)

    for idx, var in enumerate(catalog_vars, 1):
        error, warning = check_individual_variable(idx, var, len(catalog_vars), warning_as_error, environ_exists)
        errors += 1 if error else 0
        warnings += 1 if warning else 0
        print_var_status_formatted(error, warning, not error and not warning, idx, len(catalog_vars), var)
        print(SEPARATOR)

    # Print summary
    print("\nSUMMARY:")
    print(f"  Total variables checked: {len(catalog_vars)}")
    print(f"  Variables present:       {len(catalog_vars) - warnings - errors}")
    print(f"  Missing with default:    {warnings} {'(treated as errors)' if warning_as_error else ''}")
    print(f"  Missing without default: {errors}")

    if errors > 0:
        print(f"\nERROR: {errors} required environment variables are missing")
    elif warnings > 0 and warning_as_error:
        print(f"\nERROR: {warnings} environment variables are using defaults but warnings are treated as errors")
    elif warnings > 0:
        print(f"\nWARNING: {warnings} environment variables are using defaults")
    else:
        print("\nSUCCESS: All required environment variables are set")

    return all_passed


class EnvironmentVariableError(Exception):
    """Base exception for environment variable errors."""

    pass


class RequiredVariableMissingError(EnvironmentVariableError):
    """Exception raised when a required environment variable is missing."""

    def __init__(self, var_name):
        self.var_name = var_name
        super().__init__(f"Required environment variable '{var_name}' is missing")


class DefaultUsedAsError(EnvironmentVariableError):
    """Exception raised when a variable with default is missing but warnings are treated as errors."""

    def __init__(self, var_name, default_value):
        self.var_name = var_name
        self.default_value = default_value
        super().__init__(
            f"Environment variable '{var_name}' is missing and using default '{default_value}', but warnings are treated as errors"
        )


def must_pass_check(
    catalog_vars: List[Dict[str, Any]], warning_as_error: bool, environ_exists: Callable[[str], bool]
) -> bool:
    """pass all checks or raise an error

    Intended to be used within services as gating code before starting an execution.
    A raise here should be caught and used to exit with the right code to trigger a blue/green rollback or health fail.

    :param catalog_vars: a loaded catalog, see load_catalog function for this.
    :param warning_as_error: fail even if the unset variables have a default value
    :param environ_exists: A function checking existence of a variable from an environ or environ definition.
    :return: warnings were found (only if not in mode warning_as_error)
    """
    warning_found = False
    for idx, var in enumerate(catalog_vars, 1):
        error, warning = check_individual_variable(idx, var, len(catalog_vars), warning_as_error, environ_exists)
        warning_found = warning if warning else warning_found
        if error and warning:
            raise DefaultUsedAsError(var["name"], var["default_value"])
        if error:
            raise RequiredVariableMissingError(var["name"])

    return warning_found

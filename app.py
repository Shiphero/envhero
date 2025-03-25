import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Union

from catalog.from_aws_task_definition import get_task_definition_checker
from catalog.from_env import exists_in_env
from catalog.scan import scan_codebase
from environment.verify import check_environment_variables
from catalog.catalog import add_tags_to_present_vars, filter_vars_by_tag, load_catalog, save_catalog

VERIFY_EPILOG = """
Sample output:
  [1/3] DATABASE_URL
    Tags:          api, worker
    Used in:       database, models
    Has default:   False
    Status:        ✓ SET
    Referenced in:
      • database/connection.py:15
      • models/base.py:42
  --------------------
  [2/3] DEBUG
    Tags:          api
    Used in:       config
    Has default:   True
    Default value: False
    Status:        ⚠ WARNING - Not set, using default: False
  --------------------
  [3/3] API_SECRET
    Tags:          api
    Used in:       auth
    Has default:   False
    Status:        ✗ ERROR - Required variable not set
  --------------------

  SUMMARY:
    Total variables checked: 3
    Variables present:       1
    Missing with default:    1
    Missing without default: 1

  ERROR: 1 required environment variables are missing
"""


def create_env_var_catalogue(
    output_file: str = "env_var_catalog.json",
    exclude_dirs: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    no_auto_tag: bool = False,
):
    """Create an initial catalog

    Generate and save the catalog.

    :param output_file: path to the file where the json marshaled catalog should be stored
    :param exclude_dirs: these directories will be ignored.
    :param exclude_patterns: paths will be ignored if these patterns are in them
    :param no_auto_tag: do not detect tags automatically
    """

    base_dir = "."

    print("Scanning codebase for os.environ.get or os.getenv calls...")
    env_var_catalog, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns, no_auto_tag)

    # Write to JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(env_var_catalog, f, indent=2)

    print(f"Found {len(env_var_catalog)} unique environment variables")
    print(f"Found {total_vars_found} total environment variable references")
    print(f"Catalog written to {output_file}")


def update_env_var_catalogue(
    output_file: str = "env_var_catalog.json",
    exclude_dirs: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    no_auto_tag: bool = False,
):
    """Update an existing environment variable catalog

    Add new variables if found or update attributes, deletion is not implemented.
    :param output_file: file where the existing catalog is stored.
    :param exclude_dirs: these directories will be ignored.
    :param exclude_patterns: paths will be ignored if these patterns are in them
    :param no_auto_tag: do not detect tags automatically
    """
    base_dir = "."

    # Load existing catalog if it exists
    existing_catalog = []
    if os.path.exists(output_file):
        existing_catalog = load_catalog(output_file)

    # Create variable lookup by name and default value

    existing_vars = {f"{var['name']}_{var.get('default_value', '')}": var for var in existing_catalog}

    # Scan the codebase for current state
    print("Scanning codebase for os.environ.get calls...")
    new_catalog_dict, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns, no_auto_tag)

    # Update existing entries and add new ones
    updated_count = 0
    added_count = 0

    for new_var in new_catalog_dict:
        key = f"{new_var['name']}_{new_var.get('default_value', '')}"
        added, updated = process_individual_var(existing_catalog, existing_vars, key, new_var)
        added_count += added
        updated_count += updated

    # Write updated catalog
    with open(output_file, "wt", encoding="utf-8") as f:
        json.dump(existing_catalog, f, indent=2)

    print(f"Updated {updated_count} existing variables")
    print(f"Added {added_count} new variables")
    print(f"The catalog now contains {len(existing_catalog)} unique environment variables")
    print(f"Found {total_vars_found} total environment variable references")
    print(f"Updated catalog written to {output_file}")


def process_individual_var(existing_catalog, existing_vars, key, new_var):
    """Process each var found from the new catalog

    :param existing_catalog: the old catalog
    :param existing_vars:variables in the old catalog
    :param key: individual var being processed
    :param new_var: var item found in the new scan
    :return:
    """
    updated_count = 0
    added_count = 0
    if key in existing_vars:
        # Update existing entry - merge locations and packages
        existing_var = existing_vars[key]

        # Add new locations
        existing_locations = (
            {(loc["file"], loc["line"]) for loc in existing_var["locations"]} if "locations" in existing_var else {}
        )
        new_locations = existing_var.get("locations", [])
        for loc in new_var["locations"]:
            loc_key = (loc["file"], loc["line"])
            if loc_key not in existing_locations:
                new_locations.append(loc)
                updated_count += 1
        existing_var["locations"] = new_locations

        # Add new packages
        existing_packages = existing_var.get("packages", [])
        for pkg in new_var.get("packages", []):
            if pkg not in existing_packages:
                existing_packages.append(pkg)
        existing_var["packages"] = existing_packages

        # Add new tags
        if "tags" not in existing_var:
            existing_var["tags"] = []
        existing_services = set(existing_var["tags"])
        for svc in new_var.get("tags", []):
            if svc not in existing_services:
                existing_var["tags"].append(svc)
    else:
        # Add new entry
        existing_catalog.append(new_var)
        existing_vars[key] = new_var
        added_count += 1
    return added_count, updated_count


def print_structured(
    env_vars: List[Dict[str, Union[str, int, List[Dict[str, Union[str, int]]], Dict[str, Union[str, int]]]]],
):
    """output json with the found discrepancies in vars"""
    output: Dict[str, Any] = {}
    for var in env_vars:
        v_name = var["name"]
        output[v_name] = {}
        if default_value := var["default_value"]:
            output[v_name]["default_value"] = default_value
        v_locations: List[Dict[str, Union[str, int]]] = var.get("locations", [])
        if locations := [{"file": loc["file"], "line": loc["line"]} for loc in v_locations]:
            output[v_name]["locations"] = locations
    print(json.dumps(output))


def check_env_vars(
    output_file: str = "env_var_catalog.json",
    exclude_dirs: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    structured_output: bool = False,
    no_auto_tag: bool = False,
):
    """
    Check for environment variables in the code that are not in the catalog
    """
    base_dir = "."

    def maybe_print(txt: str):
        if structured_output:
            return
        print(str)

    # Load existing catalog if it exists
    if not os.path.exists(output_file):
        print(f"Catalog file {output_file} not found")
        return

    try:
        with open(output_file, encoding="utf-8") as f:
            existing_catalog = json.load(f)
        maybe_print(f"Loaded catalog with {len(existing_catalog)} variables")
    except json.JSONDecodeError:
        print("Error loading catalog: Invalid JSON format")
        return

    # Create a set of existing variables by name and default
    existing_vars = {f"{var['name']}_{var['default_value']}" for var in existing_catalog}

    # Scan the codebase for current state
    maybe_print("Scanning codebase for os.environ.get calls...")
    current_vars_list, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns, no_auto_tag)

    # Find missing variables
    missing_vars: List[Dict[str, Union[str, int, List[Dict[str, Union[str, int]]], Dict[str, Union[str, int]]]]] = []
    for var_info in current_vars_list:
        key = f"{var_info['name']}_{var_info['default_value']}"
        if key not in existing_vars:
            missing_vars.append(var_info)

    if missing_vars:
        if structured_output:
            print_structured(missing_vars)
            return  # TODO: Maybe Exit(1)?
        maybe_print(f"WARNING: Found {len(missing_vars)} environment variables in code that are not in the catalog:")
        for var in missing_vars:
            locations = ", ".join([f"{loc['file']}:{loc['line']}" for loc in var["locations"][:3]])
            if len(var["locations"]) > 3:
                locations += f" and {len(var['locations']) - 3} more"
            maybe_print(f"- {var['name']} (default: {var['default_value']}) in {locations}")
    else:
        maybe_print("All environment variables in code are documented in the catalog.")


def main():
    parser = argparse.ArgumentParser(description="Environment Variables Catalog Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    def add_common_exclude_args(common_parser):
        common_parser.add_argument(
            "--exclude-dir",
            action="append",
            default=[".venv", "__pycache__", ".git"],
            help="Directory to exclude (can be used multiple times)",
        )
        common_parser.add_argument(
            "--exclude-pattern", action="append", default=[], help="Pattern to exclude (can be used multiple times)"
        )
        common_parser.add_argument("--no-auto-tag", action="store_true", help="do not infer tags from base folders")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new catalog")
    create_parser.add_argument(
        "-o", "--output", default="env_var_catalog.json", help="Output file name (default: env_var_catalog.json)"
    )
    add_common_exclude_args(create_parser)

    # Update command
    update_parser = subparsers.add_parser("update", help="Update an existing catalog")
    update_parser.add_argument(
        "-o", "--output", default="env_var_catalog.json", help="Catalog file to update (default: env_var_catalog.json)"
    )
    add_common_exclude_args(update_parser)

    # Check command
    check_parser = subparsers.add_parser("check", help="Check for uncatalogued variables")
    check_parser.add_argument(
        "-c",
        "--catalog",
        default="env_var_catalog.json",
        help="Catalog file to check against (default: env_var_catalog.json)",
    )
    check_parser.add_argument(
        "-s", "--structured-output", action="store_true", help="return json in stdout with the findings"
    )
    add_common_exclude_args(check_parser)

    verify_parser = subparsers.add_parser(
        "verify",
        description="Verify that all variables for a given tag from the catalog are declared",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=VERIFY_EPILOG,
    )
    verify_parser.add_argument(
        "-c",
        "--catalog",
        default="env_var_catalog.json",
        help="Catalog file to check against (default: env_var_catalog.json)",
    )
    verify_parser.add_argument(
        "-t", "--tag", action="append", default=[], help="Service name to check (can be specified multiple times)"
    )
    verify_parser.add_argument(
        "--warning-as-error", action="store_true", help="Treat missing variables with defaults as errors"
    )
    verify_parser.add_argument("--help-examples", action="store_true", help="Show usage examples and sample output")

    tags_from_env_parser = subparsers.add_parser(
        "tags_from_env",
        description="Adds the passed tags to the vars that are present in the catalog and the current env.",
    )

    tags_from_env_parser.add_argument(
        "-t", "--tag", action="append", default=[], help="Service name to check (can be specified multiple times)"
    )
    tags_from_env_parser.add_argument(
        "-c",
        "--catalog",
        default="env_var_catalog.json",
        help="Catalog file to check against (default: env_var_catalog.json)",
    )
    tags_from_env_parser.add_argument(
        "-o", "--output", default="", help="Catalog file to update (default: env_var_catalog.json)"
    )

    tags_from_env_parser.add_argument(
        "-d",
        "--definition",
        help="A path to a json file definition or the name of a definition, if the file is not found we will try with aws.",
    )

    args = parser.parse_args()

    if args.command == "create":
        create_env_var_catalogue(
            output_file=args.output,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern,
            no_auto_tag=args.no_auto_tag,
        )
    elif args.command == "update":
        update_env_var_catalogue(
            output_file=args.output,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern,
            no_auto_tag=args.no_auto_tag,
        )
    elif args.command == "check":
        check_env_vars(
            output_file=args.catalog,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern,
            structured_output=args.structured_output,
            no_auto_tag=args.no_auto_tag,
        )
    elif args.command == "verify":
        catalog = load_catalog(args.catalog)
        print(f"Loaded catalog with {len(catalog)} environment variables")
        if hasattr(args, "definition") and args.definition:
            # if this is not a file then likely we are trying to pull from aws
            use_aws = not os.path.isfile(args.definition)
            env_checker = get_task_definition_checker(args.definition, use_aws)
        else:
            env_checker = exists_in_env
        if args.tag:
            tags = args.tag
            filtered_vars = filter_vars_by_tag(catalog, tags)
            print(f"Filtered to {len(filtered_vars)} variables used in service(s): {', '.join(tags)}")
        else:
            filtered_vars = catalog
            print("No tags filter specified, checking all variables in catalog")
        all_passed = check_environment_variables(
            catalog_vars=filtered_vars, warning_as_error=args.warning_as_error, environ_exists=env_checker
        )
        sys.exit(0 if all_passed else 1)
    elif args.command == "tags_from_env":
        catalog = load_catalog(args.catalog)
        print(f"Loaded catalog with {len(catalog)} environment variables")
        if args.definition:
            # if this is not a file then likely we are trying to pull from aws
            use_aws = not os.path.isfile(args.definition)
            env_checker = get_task_definition_checker(args.definition, use_aws)
        else:
            env_checker = exists_in_env
        catalog = add_tags_to_present_vars(catalog, args.tag, env_checker)
        output_file = args.output if args.output else args.catalog
        save_catalog(catalog, output_file)
    else:
        parser.print_help()

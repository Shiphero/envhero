import argparse
import json
import os
from typing import Any, Dict, List, Optional, Union

from catalog.scan import scan_codebase

def create_env_var_catalogue(output_file: str = "env_var_catalog.json",
                             exclude_dirs: Optional[List[str]]=None, exclude_patterns: Optional[List[str]]=None):
    """Create an initial catalog

    Generate and save the catalog.

    :param output_file: path to the file where the json marshaled catalog should be stored
    :param exclude_dirs: these directories will be ignored.
    :param exclude_patterns: paths will be ignored if these patterns are in them
    """

    base_dir = "."

    print("Scanning codebase for os.environ.get or os.getenv calls...")
    env_var_catalog, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns)

    # Convert to list for the final JSON structure
    catalog_list = list(env_var_catalog.values())

    # Write to JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(catalog_list, f, indent=2)

    print(f"Found {len(catalog_list)} unique environment variables")
    print(f"Found {total_vars_found} total environment variable references")
    print(f"Catalog written to {output_file}")


def update_env_var_catalogue(output_file: str = "env_var_catalog.json",
                             exclude_dirs: Optional[List[str]]=None, exclude_patterns: Optional[List[str]]=None):
    """Update an existing environment variable catalog

    Add new variables if found or update attributes, deletion is not implemented.
    :param output_file: file where the existing catalog is stored.
    :param exclude_dirs: these directories will be ignored.
    :param exclude_patterns: paths will be ignored if these patterns are in them
    """
    base_dir = "."

    # Load existing catalog if it exists
    existing_catalog = []
    if os.path.exists(output_file):
        try:
            with open(output_file, encoding="utf-8") as f:
                existing_catalog = json.load(f)
            print(f"Loaded existing catalog with {len(existing_catalog)} variables")
        except json.JSONDecodeError:
            print("Error loading existing catalog: Invalid JSON format")
            return

    # Create variable lookup by name and default value
    existing_vars = {f"{var['name']}_{var['default_value']}": var for var in existing_catalog}

    # Scan the codebase for current state
    print("Scanning codebase for os.environ.get calls...")
    new_catalog_dict, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns)

    # Update existing entries and add new ones
    updated_count = 0
    added_count = 0

    for key, new_var in new_catalog_dict.items():
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
        existing_locations = {(loc["file"], loc["line"]) for loc in existing_var["locations"]}
        for loc in new_var["locations"]:
            loc_key = (loc["file"], loc["line"])
            if loc_key not in existing_locations:
                existing_var["locations"].append(loc)
                updated_count += 1

        # Add new packages
        for pkg in new_var["packages"]:
            if pkg not in existing_var["packages"]:
                existing_var["packages"].append(pkg)

        # Add new tags
        if "services" not in existing_var:
            existing_var["tags"] = []
        existing_services = set(existing_var["tags"])
        for svc in new_var["tags"]:
            if svc not in existing_services:
                existing_var["tags"].append(svc)
    else:
        # Add new entry
        existing_catalog.append(new_var)
        existing_vars[key] = new_var
        added_count += 1
    return added_count, updated_count

def print_structured(vars: List[Dict[str,Union[str,int,List[Dict[str,Union[str,int]]],Dict[str,Union[str,int]]]]]):
    """output json with the found discrepancies in vars"""
    for var in vars:
        output: Dict[str,Any] = {}
        v_name = var["name"]
        output[v_name] = {}
        if default_value := var['default_value']:
            output[v_name]["default_value"] = default_value
        v_locations:List[Dict[str, Union[str,int]]] = var["locations"]
        if locations:=[{"file":loc["file"], "line":loc["line"]} for loc in v_locations]:
            output[v_name]["locations"] = locations
        print(json.dumps(output))


def check_env_vars(output_file: str = "env_var_catalog.json",
                   exclude_dirs: Optional[List[str]]=None, exclude_patterns: Optional[List[str]]=None,
                   structured_output: bool = False):
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
    current_vars_dict, total_vars_found = scan_codebase(base_dir, exclude_dirs, exclude_patterns)

    # Find missing variables
    missing_vars:List[Dict[str,Union[str,int,List[Dict[str,Union[str,int]]],Dict[str,Union[str,int]]]]] = []
    for key, var_info in current_vars_dict.items():
        if key not in existing_vars:
            missing_vars.append(var_info)

    if missing_vars:
        if structured_output:
            print_structured(missing_vars)
            return # TODO: Maybe Exit(1)?
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

    def add_common_exclude_args(parser):
        parser.add_argument(
            "--exclude-dir",
            action="append",
            default=[".venv", ".venv-py3.8", "__pycache__", ".git"],
            help="Directory to exclude (can be used multiple times)"
        )
        parser.add_argument(
            "--exclude-pattern",
            action="append",
            default=[],
            help="Pattern to exclude (can be used multiple times)"
        )
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
            "-s",
            "--structured-output",
            default=False,
            type=bool,
            help="return json in stdout with the findings"
    )
    add_common_exclude_args(check_parser)


    args = parser.parse_args()

    if args.command == "create":
        create_env_var_catalogue(
            output_file=args.output,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern
        )
    elif args.command == "update":
        update_env_var_catalogue(
            output_file=args.output,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern
        )
    elif args.command == "check":
        check_env_vars(
            output_file=args.catalog,
            exclude_dirs=args.exclude_dir,
            exclude_patterns=args.exclude_pattern,
            structured_output=args.structured_output,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

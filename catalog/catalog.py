import json
import sys
from typing import Any, Callable, Dict, List


def load_catalog(catalog_path: str) -> List[Dict[str, Any]]:
    """Load the environment variable catalog from JSON."""
    try:
        with open(catalog_path) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"ERROR: Catalog file '{catalog_path}' not found")
    except json.JSONDecodeError:
        sys.exit(f"ERROR: Catalog file '{catalog_path}' contains invalid JSON")


def filter_vars_by_tag(catalog: List[Dict[str, Any]], tags: List[str]) -> List[Dict[str, Any]]:
    """Filter catalog entries that belong to the tags or have no tag"""
    if not tags:
        return catalog

    filtered_vars = []
    for var in catalog:
        # Include variables used in any of the specified services or marked for all services
        var_tags = var.get("tags", [])
        if "__all__" in var_tags or any(tag in var_tags for tag in tags):
            filtered_vars.append(var)

    return filtered_vars


def save_catalog(catalog: List[Dict[str, Any]], output_path: str) -> None:
    """
    Save the environment variable catalog to a JSON file.

    :param catalog: The environment variable catalog to save
    :param output_path: Path where to save the catalog
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, sort_keys=True)
        print(f"Successfully saved catalog with {len(catalog)} variables to '{output_path}'")
    except IOError as e:
        sys.exit(f"ERROR: Failed to write catalog to '{output_path}': {str(e)}")


def add_tags_to_present_vars(
    catalog: List[Dict[str, Any]], tags: List[str], environ_exists: Callable[[str], bool]
) -> List[Dict[str, Any]]:
    """
    Add tags to variables in the catalog that are present in the environment.

    :param catalog: The environment variable catalog
    :param tags: List of tags to add to present environment variables
    :param environ_exists: A function checking existence of a variable from an environ or environ definition.
    :return: The updated catalog
    """
    if not tags:
        return catalog

    for var in catalog:
        var_name = var["name"]
        if environ_exists(var_name):
            var_tags = var.get("tags", [])
            for tag in tags:
                if tag not in var_tags:
                    var_tags.append(tag)
            var["tags"] = var_tags

    return catalog

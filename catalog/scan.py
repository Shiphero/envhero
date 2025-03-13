import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Union

from catalog import EnvVarVisitor
from catalog.visitor import UNKNOWN


def find_base_tag(file_path: Path) -> str:
    """Determine tag from package structure

    Find the base tag attempts to determine the tags that apply to a file path
    by determining the outermost package

    :param file_path: the path to the file being analized
    :return: found tag, if any.
    """
    parts = file_path.parts
    if len(parts) > 1:
        # Return the first meaningful directory in the path
        for part in parts:
            if part not in [".", "..", "src", "lib"] and not part.endswith(".py"):
                return part

    return ""


def find_package_name(file_path: Path) -> str:
    """Attempt to identify the package

    Best effort attempt at figuring what package a file belongs to based on directory structure
    """
    parts = file_path.parts

    # Look for common package indicators
    for i, part in enumerate(parts):
        if i > 0 and parts[i - 1] in ["src", "lib", "packages"]:
            return part

        # Handle typical Python package structure
        if part.endswith(".py") and i > 0:
            return parts[i - 1]

    # Fallback: use directory name
    parent_dir = file_path.parent.name
    if parent_dir != ".":
        return parent_dir

    return "unknown_package"

def scan_codebase(base_dir: str, exclude_dirs: List[str], exclude_patterns: List[str]) -> Tuple[Dict[str,Dict[str,Union[str,Set,List]]], int]:
    """Scan Python files for os.environ.get calls and catalog them

    :param base_dir: path where to start the recursive scan
    :param exclude_dirs: directories to exclude
    :paran exclude_patterns: if the directory contains these, ignore.
    :return: dict containing the full catalog and number of total found variable uses
    """
    env_var_catalog: Dict[str,Dict[str,Union[str,Set,List]]] = {}
    total_vars_found = 0

    for root, dirs, files in os.walk(base_dir):
        # remove excluded dirs, this is quite a naive match
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            # bail early if not python
            if not file.endswith(".py"):
                continue

            file_path = Path(os.path.join(root, file))
            relative_path = file_path.relative_to(base_dir)

            # bail if any of the excluded patterns is present in the relative path
            if any(True for exclude in exclude_patterns if exclude in str(relative_path)):
                continue

            package_name = find_package_name(relative_path)
            base_tag = find_base_tag(relative_path)

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Parse the file
                tree = ast.parse(content)
                # Give it to the visitor class
                visitor = EnvVarVisitor()
                visitor.visit(tree)

                # Add found environment variables to the catalog
                for var_info in visitor.env_vars:
                    total_vars_found += 1
                    var_name = var_info["name"]
                    var_key = f"{var_name}_{var_info['default_value']}"
                    inferred_type = var_info["inferred_type"]

                    if var_key not in env_var_catalog:
                        env_var_catalog[var_key] = {
                            "name": var_name,
                            "has_default": var_info["has_default"],
                            "default_value": var_info["default_value"],
                            "packages": set(),
                            "tags": {base_tag},
                            "locations": [],
                            "inferred_type": inferred_type if inferred_type and inferred_type != UNKNOWN else ""
                        }
                    else:
                        env_var_catalog[var_key]["tags"].add(base_tag)
                        # Maybe update inferred type if we have something better
                        it = env_var_catalog[var_key]["inferred_type"]
                        env_var_catalog[var_key]["inferred_type"] = inferred_type if inferred_type and inferred_type != UNKNOWN and not it else it

                    env_var_catalog[var_key]["packages"].add(package_name)
                    env_var_catalog[var_key]["locations"].append(
                        {"file": str(relative_path), "line": var_info["lineno"]}
                    )

            except Exception as e:
                print(f"Error processing {file_path}: {e}", file=sys.stderr)
                raise e

    # Convert sets to lists for JSON serialization
    for var_info in env_var_catalog.values():
        var_info["packages"] = list(var_info["packages"])
        var_info["tags"] = list(var_info["tags"])

    return env_var_catalog, total_vars_found



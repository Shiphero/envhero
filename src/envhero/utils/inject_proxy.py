import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Callable, Optional


def create_var_proxy_module(base_dir: str = ".") -> bool:
    """Create the var_handler module with var_proxy if it doesn't exist.

    Args:
        base_dir: Base directory where the module should be created

    Returns:
        bool: True if module was created, False if it already existed
    """
    module_dir = Path(base_dir) / "var_handler"
    module_file = module_dir / "__init__.py"

    # Check if module already exists
    if module_file.exists():
        return False

    # Create the directory
    module_dir.mkdir(exist_ok=True)

    # Create the module file
    module_content = '''
from proxy.vars import VarProxy
import os

# Create singleton instance that will be used across the application
var_proxy = VarProxy(
    getenv_callable=os.environ.get,
    visited_callback=None
)
"""Instantiate a single proxy for environment variables.

This is an instance of envhero.vars.VarProxy (https://github.com/ShipHero/envhero)
Please take a moment to go through the documentation and see what configuration you have available.
There is a possibility to add a callback to be invoked the first time a variable is accessed
so you can use this to discover your variables actually in use in different circumstances.
"""
'''
    module_file.write_text(module_content.strip())
    return True


def transform_file(file_path: str) -> bool:
    """Transform a Python file to use var_proxy.get instead of direct OS environment access.

    This function uses regex pattern matching rather than AST parsing due to AST being unreliable
    to maintain the existing code as is and only potentially generating equivalent code.

    Args:
        file_path: Path to the Python file to transform

    Returns:
        bool: True if the file was changed, False otherwise
    """
    try:
        with open(file_path, "r") as f:
            content = f.read()

        # Define patterns for os.getenv and os.environ.get
        getenv_pattern = r"os\.getenv\((.*?)\)"
        environ_get_pattern = r"os\.environ\.get\((.*?)\)"

        # Check if the file contains any of the patterns
        has_getenv = re.search(getenv_pattern, content)
        has_environ_get = re.search(environ_get_pattern, content)

        if not (has_getenv or has_environ_get):
            return False

        # Add import if needed
        if "from var_handler import var_proxy" not in content:
            # Try to find where imports end using a more comprehensive approach
            lines = content.split("\n")

            # Find the last line that's part of an import statement
            last_import_line = -1
            in_multiline_import = False
            open_parens = 0

            for i, line in enumerate(lines):
                line_stripped = line.strip()

                # Track multi-line imports with parentheses
                if "(" in line:
                    open_parens += line.count("(")
                if ")" in line:
                    open_parens -= line.count(")")

                # Check if this is an import line
                is_import = line_stripped.startswith(("import ", "from "))
                is_continued_import = in_multiline_import or open_parens > 0

                if is_import or is_continued_import:
                    last_import_line = i
                    in_multiline_import = not line_stripped.endswith(";") and (
                        line_stripped.endswith("\\") or open_parens > 0
                    )
                elif not is_continued_import:
                    # If we're not in a continued import and this isn't an import line,
                    # only update if we already found an import (to avoid early exit)
                    if last_import_line >= 0:
                        break

            # Insert after the last import or at the beginning with newlines
            if last_import_line >= 0:
                lines.insert(last_import_line + 1, "from var_handler import var_proxy")
                content = "\n".join(lines)
            else:
                content = "from var_handler import var_proxy\n\n" + content

        # Replace os.getenv with var_proxy.get
        content = re.sub(getenv_pattern, r"var_proxy.get(\1)", content)

        # Replace os.environ.get with var_proxy.get
        content = re.sub(environ_get_pattern, r"var_proxy.get(\1)", content)

        # Write the changed content back to the file
        with open(file_path, "w") as f:
            f.write(content)

        return True
    except Exception as e:
        print(f"Error transforming {file_path}: {e}", file=sys.stderr)
        return False


def should_exclude(file_path: str, exclude_patterns: List[str]) -> bool:
    """
    Check if a file should be excluded based on patterns.

    Args:
        file_path: Path to check
        exclude_patterns: List of regex patterns to exclude

    Returns:
        bool: True if the file should be excluded
    """
    for pattern in exclude_patterns:
        if re.search(pattern, file_path):
            return True
    return False


def transform_directory(
    directory: str,
    exclude_dirs: List[str] = None,
    exclude_patterns: List[str] = None,
    formatter_callback: Optional[Callable[[List[str]], None]] = None,
) -> Tuple[int, int, List[str]]:
    """Transform all Python files in a directory to use var_proxy.get.

    Args:
        directory: Root directory to start the transformation
        exclude_dirs: List of directory names to exclude
        exclude_patterns: List of file patterns to exclude
        formatter_callback: Optional callback to run formatter on modified files

    Returns:
        Tuple[int, int, List[str]]: (files processed, files changed, list of changed files)
    """
    if exclude_dirs is None:
        exclude_dirs = ["venv", ".git", "__pycache__", ".env"]

    if exclude_patterns is None:
        exclude_patterns = []

    # Create the var_proxy module if it doesn't exist
    created = create_var_proxy_module(directory)
    if created:
        print(f"Created var_handler module in {directory}")

    files_processed = 0
    files_changed = 0
    changed_files = []

    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)

                # Skip files matching exclude patterns
                if should_exclude(file_path, exclude_patterns):
                    continue

                # Don't transform the var_handler module itself
                if "var_handler" in file_path.split(os.path.sep):
                    continue

                files_processed += 1
                changed = transform_file(file_path)

                if changed:
                    files_changed += 1
                    changed_files.append(file_path)
                    print(f"Transformed: {file_path}")

    # Run formatter on changed files if callback provided
    if formatter_callback and changed_files:
        formatter_callback(changed_files)

    return files_processed, files_changed, changed_files


def default_formatter(changed_files: List[str]) -> None:
    """Default formatter that runs ruff on changed files.

    Args:
        changed_files: List of modified file paths
    """
    try:
        import subprocess

        print("Running formatter on changed files...")

        # Try to run ruff format
        try:
            subprocess.run(["ruff", "format"] + changed_files, check=True)
            print("Formatting completed successfully with ruff")
        except (subprocess.SubprocessError, FileNotFoundError):
            # Fall back to black if ruff is not available
            try:
                subprocess.run(["black"] + changed_files, check=True)
                print("Formatting completed successfully with black")
            except (subprocess.SubprocessError, FileNotFoundError):
                print("Warning: Could not run formatter (ruff or black). Please format files manually.")
    except Exception as e:
        print(f"Error running formatter: {e}", file=sys.stderr)

import os
from typing import Any


def from_env_getter(var_name: str) -> (Any, bool):
    """return the variable from environment

    returns the value, if found (or None) and a boolean indicating
    if it was set or not, to avoid default value confusions.
    """
    return os.environ.get(var_name), var_name in os.environ


def exists_in_env(var_name: str) -> bool:
    """return true if variable is defined in environment"""
    return var_name in os.environ

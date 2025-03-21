import json
import boto3
from typing import Callable, Dict, Optional, Union, Any
from pathlib import Path


def get_env_vars_from_task_definition(
    task_definition: Union[str, Dict[str, Any]], use_aws_api: bool = False, region: Optional[str] = None
) -> Dict[str, bool]:
    """
    Extract environment variables from an AWS ECS Task Definition.

    Args:
        task_definition: Either a path to a JSON file containing the task definition,
                        a task definition name (when use_aws_api=True), or a dictionary
                        containing the task definition.
        use_aws_api: If True, task_definition is treated as a task definition name to fetch from AWS.
        region: AWS region to use when fetching from AWS API. Defaults to boto3's default region.

    Returns:
        Dictionary mapping environment variable names to a boolean (True) indicating presence

    Example:
        # From a local file
        env_vars = get_env_vars_from_task_definition('path/to/task-definition.json')

        # From AWS API
        env_vars = get_env_vars_from_task_definition('my-service-task-def', use_aws_api=True, region='us-west-2')

        # From an existing dictionary
        env_vars = get_env_vars_from_task_definition(task_def_dict)
    """
    # Load the task definition based on input type
    task_def_data = None

    if use_aws_api and isinstance(task_definition, str):
        # Fetch from AWS API
        client = boto3.client("ecs", region_name=region)
        response = client.describe_task_definition(taskDefinition=task_definition)
        task_def_data = response.get("taskDefinition", {})
    elif isinstance(task_definition, str) and not use_aws_api:
        # Load from file
        try:
            with open(Path(task_definition), "r") as f:
                task_def_data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to load task definition from file: {e}")
    elif isinstance(task_definition, dict):
        # Use provided dictionary
        task_def_data = task_definition
    else:
        raise ValueError("task_definition must be a file path, task definition name, or dictionary")

    # Extract environment variables from all container definitions
    env_vars = {}

    # Process container definitions
    container_definitions = task_def_data.get("containerDefinitions", [])
    for container in container_definitions:
        # Process environment variables defined directly
        for env_var in container.get("environment", []):
            name = env_var.get("name")
            if name:
                env_vars[name] = env_var.get("value")

        # Process environment variables from secrets
        for secret in container.get("secrets", []):
            name = secret.get("name")
            if name:
                env_vars[name] = len(secret.get("value")) > 0

    return env_vars


def get_task_definition_checker(
    task_definition: Union[str, Dict[str, Any]], use_aws_api: bool = False, region: Optional[str] = None
) -> Callable[[str], bool]:
    """
    Returns a function that checks if variables exist in a task definition.

    Instead of looking up the task definition each time, this retrieves all environment
    variables once and returns a function that can be called repeatedly to check for
    specific variables.

    Args:
        task_definition: Either a path to a JSON file containing the task definition,
                        a task definition name (when use_aws_api=True), or a dictionary
                        containing the task definition.
        use_aws_api: If True, task_definition is treated as a task definition name to fetch from AWS.
        region: AWS region to use when fetching from AWS API.

    Returns:
        A function that takes a variable name and returns True if it exists in the task definition

    Example:
        # Create the checker function
        checker = get_task_definition_checker('path/to/task-definition.json')

        # Use it multiple times without a reload of the source.
        if checker('DATABASE_URL'):
            print('Database URL is defined')
        if checker('API_KEY'):
            print('API key is defined')
    """
    # Retrieve all environment variables once
    env_vars = get_env_vars_from_task_definition(task_definition, use_aws_api, region)

    # Return a closure that checks if a variable exists in the pre-loaded dictionary
    def var_exists(var_name: str) -> bool:
        return var_name in env_vars

    return var_exists

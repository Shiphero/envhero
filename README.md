# EnvHero

This tool aims at improving the resiliency of python services that might make
use of environment variables.

It requires human convention but is quite helpful at reducing potencial
for human error.

## Rationale

As codebases and number of contributors grow, there are certain moving
parts that become difficult to orchestrate.

For most of the configuration parts there are established tools and infrastructure that help in coordinating
so new needs and components by one team are reflected throughout the organization.

Environment variables are not, for the most part, in this category.  It is possible that their use began as local
by one or several teams and then grew to be shared and a requirement which must be managed by the ops team.

We aim with this set of tools and libraries at helping teams order their existing catalog of environment
variables and keep them up to date and properly documented going forward.

It is worth mentioning that, if your team is beginning on a project and there is a established disciplined 
culture of maintained human created metadata, there are other tools available. A good example is [EnvGuardian](
https://github.com/femitubosun/EnvGuardian
) which allows tracking of said variables albeit by hand.

## Features
* Create and update an environment variables catalog
* Perform checks of variables in code and missing from catalog.
* Scan environment and issue report of missing environment variables
* Auto tag from existing environment
* Invoke as a function pre-execution of entrypoint and fail early if variables are missing

## Usage

# EnvHero Usage Documentation

## As a Library

### Scanning

```python
from envhero.catalog import scan_codebase, print_structured

# Scan for environment variables in your codebase
vars_dict, total_found = scan_codebase(
    base_dir=".", 
    exclude_dirs=[".venv", "__pycache__", ".git"], 
    exclude_patterns=["*.pyc"],
    no_auto_tag=False
)

# Print findings in structured format
print_structured(vars_dict.values())
```

### Guarding

```python
from envhero.catalog import load_catalog, filter_vars_by_tag
from envhero.environment import RequiredVariableMissingError, DefaultUsedAsErrorError, must_pass_check

try:
    # Load your environment variable catalog
    catalog = load_catalog("env_var_catalog.json")
    
    # Filter variables by service tags if needed
    service_vars = filter_vars_by_tag(catalog, ["api", "worker"])
    
    # Check required environment variables before starting application
    must_pass_check(service_vars, warning_as_error=True)
    
    # If we get here, all required environment variables are set
    start_application()
    
except RequiredVariableMissingError as e:
    print(f"ERROR: Missing required environment variable: {e.var_name}")
    sys.exit(1)
except DefaultUsedAsErrorError as e:
    print(f"ERROR: Using default value for {e.var_name} ({e.default_value}) but warnings are treated as errors")
    sys.exit(1)
```

## As a Tool
For easy use, create an alias. Here is an example for bashrc

```bash
echo "alias envhero=\"\$(pwd)/src/envhero/__main__.py\"" >> ~/.bashrc && source ~/.bashrc
```

### Creating a Catalog

```bash
envhero create -o env_var_catalog.json --exclude-dir tests --exclude-dir .venv
```

<span style="color:red">NOTE</span>: This command generates a complete catalog of environment variables, inferring tags based on the folder where the application is stored. To prevent these tags from being inferred, use `--no-auto-tag`.

Output:

```
Scanning codebase for os.environ.get calls...
Found 15 environment variable usages in 7 files
Successfully saved catalog with 15 variables to 'env_var_catalog.json'
```

### Updating an Existing Catalog

```bash
envhero update -o env_var_catalog.json
```

Output:
```
Loaded catalog with 15 variables
Scanning codebase for os.environ.get calls...
Found 2 new environment variable usages
Updated catalog now contains 17 variables
```

### Checking for Uncatalogued Variables

```bash
envhero check -c env_var_catalog.json
```

Output:
```
Loaded catalog with 17 variables
Scanning codebase for os.environ.get calls...
WARNING: Found 2 environment variables in code that are not in the catalog:
- API_TIMEOUT (default: 30) in api/client.py:45, api/utils.py:12 and 1 more
- DEBUG_MODE (default: False) in core/settings.py:23
```

With structured output:
```bash
envhero check -c env_var_catalog.json --structured-output
```

Output:
```json
[
  {
    "name": "API_TIMEOUT",
    "default_value": 30,
    "has_default": true,
    "locations": [
      {"file": "api/client.py", "line": 45},
      {"file": "api/utils.py", "line": 12},
      {"file": "services/api.py", "line": 78}
    ]
  },
  {
    "name": "DEBUG_MODE",
    "default_value": false,
    "has_default": true,
    "locations": [
      {"file": "core/settings.py", "line": 23}
    ]
  }
]
```

### Verifying Environment Variables

```bash
envhero verify -c env_var_catalog.json -t api -t worker
```

Output:
```
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
```

With strict validation:
```bash
envhero verify -c env_var_catalog.json -t api --warning-as-error
```

Output:
```
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

  ERROR: 2 required environment variables are missing
```

### Adding Tags to Variables from An Environment

#### From a shell

This command scans all environment variables currently present in the shell and assigns the tags `test1` and `test2` to all matching environment variables in the catalog.

```bash
envhero tags_from_env -c env_var_catalog.json -t test1 -t test2
```

#### From an AWS task definition file

Given the path to a task definition file, this command tags with `application-x` the matching variables in the catalog.

```bash
envhero tags_from_env -c env_var_catalog.json -d task_definition.json -t application-x
```

#### From an AWS task definition

Same as previous but using remote task definitions instead of local files.

```bash
export AWS_ACCESS_KEY_ID=xxxxxxx
export AWS_SECRET_ACCESS_KEY=xxxxxxx
export AWS_SESSION_TOKEN=xxxxxxx
export AWS_DEFAULT_REGION=xxxxxxx #beware boto3 does not support AWS_REGION
envhero tags_from_env -c env_var_catalog.json -d task_definition_name -t production -t high-memory
```
<span style="color:red">NOTE</span>: If you are an SSO user, bear in mind that this also works perfectly with AWS profiles.

Output:
```
Loaded catalog with 17 environment variables
Added tags to 12 variables present in environment
Successfully saved catalog with 17 variables to 'env_var_catalog.json'
```

With custom output:
```bash
envhero tags_from_env -c env_var_catalog.json -t staging -o updated_catalog.json
```

Output:
```
Loaded catalog with 17 environment variables
Added tags to 12 variables present in environment
Successfully saved catalog with 17 variables to 'updated_catalog.json'
```
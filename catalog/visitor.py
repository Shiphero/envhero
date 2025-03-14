import ast

UNKNOWN = "unknown"


class EnvVarVisitor(ast.NodeVisitor):
    """AST visitor to find os.environ.get or os.getenv calls"""

    def __init__(self):
        self.env_vars = []
        self.current_parent = None

    @staticmethod
    def is_env_get_call(node: ast.AST):
        """Determine if the node is a call to an os_environ retrieving function"""

        is_os_environ_get = (
            # Are we calling a method
            isinstance(node.func, ast.Attribute)
            # is the method on another object (os.environ)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            # is the base object a named variable? (os)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
            # is this a call to the get method with one arg that is a constant (string)
            # we do NOT support os.environ.get(variable)
            and node.func.attr == "get"
            and len(node.args) > 0
            and isinstance(node.args[0], ast.Constant)
        )

        is_os_getenv = (
            # Are we calling a method
            isinstance(node.func, ast.Attribute)
            # is the method on a named variable? (os)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            # is this a call to getenv method with one arg that is a contant?
            # we do NOT support os.getenv(variable)
            and node.func.attr == "getenv"
            and len(node.args) > 0
            and isinstance(node.args[0], ast.Constant)
        )
        return is_os_getenv or is_os_environ_get

    @staticmethod
    def extract_union_types(annotation_node):
        """Extract types from Union or Optional type annotations"""
        if isinstance(annotation_node, ast.Tuple):
            # For Union[str, int] etc.
            types = []
            for elt in annotation_node.elts:
                if isinstance(elt, ast.Name):
                    types.append(elt.id)
                else:
                    types.append(UNKNOWN)
            return f"Union[{', '.join(types)}]"
        elif isinstance(annotation_node, ast.Name):
            # For simpler cases
            return annotation_node.id
        return UNKNOWN

    def visit(self, node):
        """Track parent node and carry on"""
        parent = self.current_parent
        old_parent = parent
        self.current_parent = node
        super().visit(node)
        self.current_parent = old_parent

    def visit_Call(self, node: ast.AST):
        """Visit implementation for callables

        A visitor class will call visit_classname if declared, this is for callables on the
        AST tree.
        """
        if self.is_env_get_call(node):
            # Get the environment variable name, we know the value of the call is the string with the variable name
            # because is_env_get_call only considers calls with a literal as first parameter.
            env_var_name = node.args[0].value

            # Check for default value
            default_value = None
            has_default = False
            inferred_type = None

            # for both calls, the second parameter is a default value.
            if len(node.args) > 1:
                has_default = True
                # For non-constant defaults, just indicate there's a default without its value
                default_value = node.args[1].value if isinstance(node.args[1], ast.Constant) else "<non-constant>"

                # Try to infer type from default value
                if isinstance(node.args[1], ast.Constant) and default_value is not None:
                    nferred_type = type(default_value).__name__

            # Try to infer type from assignment context
            parent = getattr(self, "current_parent", None)
            if not inferred_type and isinstance(parent, ast.Assign):
                # Check if the target has type annotations
                target = parent.targets[0]
                if isinstance(target, ast.Name) and hasattr(target, "annotation") and target.annotation:
                    if isinstance(target.annotation, ast.Name):
                        inferred_type = target.annotation.id
                    elif isinstance(target.annotation, ast.Subscript):
                        if isinstance(target.annotation.value, ast.Name):
                            base_type = target.annotation.value.id
                            if base_type == "Optional" or base_type == "Union":
                                # Extract from Optional[Type] or Union[Type, ...]
                                if isinstance(target.annotation.slice, ast.Index):  # Python 3.8
                                    inferred_type = self.extract_union_types(target.annotation.slice.value)
                                else:  # Python 3.9+
                                    inferred_type = self.extract_union_types(target.annotation.slice)
                            else:
                                inferred_type = f"{base_type}[...]"

            self.env_vars.append(
                {
                    "name": env_var_name,
                    "has_default": has_default,
                    "default_value": default_value,
                    "lineno": node.lineno,
                    "inferred_type": inferred_type,
                }
            )

        # Continue searching in children nodes
        self.generic_visit(node)

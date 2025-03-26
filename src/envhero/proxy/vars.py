from typing import Any, Callable, Dict, Optional
import threading


class VarProxy:
    """
    A thread-safe proxy for accessing environment variables with caching.

    This class wraps environment variable access by caching values to avoid repeated
    lookups and providing optional callback notifications when variables are accessed.
    It provides a thread-safe implementation using a reentrant lock to protect the
    internal cache from concurrent modifications.

    The proxy caches the raw value from the environment without applying defaults
    during storage. Defaults are only applied when returning values to callers if
    the actual environment variable is not set or is None.
    """

    def __init__(
        self,
        getenv_callable: Callable[[str, Optional[Any]], Any],
        visited_callback: Optional[Callable[[str, bool], None]] = None,
    ):
        """Construct a thread-safe environment variable proxy with caching.

        Args:
            getenv_callable: A function that retrieves environment variables given a name.
                             Should take a variable name (str) and return its value or None.
                             This function should not handle defaults as VarProxy manages them, but
                             they are accepted as part of the signature to satisfy the default callable signature
                             which is os.environ.get or os.getenv.
            visited_callback: Optional callback function that will be called when a variable
                              is accessed for the first time. Receives three arguments:
                              - variable_name (str): Name of the accessed variable
                              - found (bool): True if on first access the variable was set.

        Example:
            >>> import os
            >>> def track_vars(name, found):
            ...     print(f"{name} looked up, found = {found}")
            >>> proxy = VarProxy(os.environ.get, track_vars)
            >>> value = proxy.get("DATABASE_URL", "sqlite:///default.db")
        """
        self._getenv_callable: Callable[[str, Optional[Any]], Any] = getenv_callable
        self._visited_callback: Optional[Callable[[str, bool], None]] = visited_callback
        self._var_cache: Dict[str, Any] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread safety

    def _get(self, variable_name: str, variable_default: Any = None) -> Any:
        """Internal accessor for the cached variables

        :param variable_name: the name of the environment variable
        :param variable_default: the default value if any
        :return: the value or default value
        """
        # First check if we have the value cached, without lock for performance
        if variable_name in self._var_cache:
            value = self._var_cache[variable_name]
            # If value is None, return the default instead, None might be just cached
            return value if value is not None else variable_default

        # Acquire lock for thread-safe modification of the cache
        with self._lock:
            # Double-check in case another thread updated the cache while we were waiting
            if variable_name in self._var_cache:
                value = self._var_cache[variable_name]
                return value if value is not None else variable_default

            # Get value from the environment
            value = self._getenv_callable(variable_name)
            # do not pass default variable because we want this for caching
            self._var_cache[variable_name] = value
            # Now set default
            found = value is not None
            value = variable_default if value is None else value

            # Notify callback if provided
            if self._visited_callback:
                # True indicates the variable was accessed, we only do this the first time.
                self._visited_callback(variable_name, found)

            return value

    def get(self, variable_name, variable_default=None):
        """Get an environment variable or its default value

        :param variable_name: the name of the environment variable
        :param variable_default: the default value if any
        :return: the value or default value
        """
        return self._get(variable_name, variable_default)

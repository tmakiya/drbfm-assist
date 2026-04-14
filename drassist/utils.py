import os
from typing import Optional


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable value.

    Args:
        key: Environment variable key
        default: Default value if key is not found

    Returns:
        Environment variable value or default value

    """
    return os.getenv(key, default)

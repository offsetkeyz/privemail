"""Email validation utilities."""
import re
from email.utils import parseaddr


def is_valid_email(email: str) -> bool:
    """Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if email appears valid, False otherwise
    """
    if not email or not isinstance(email, str):
        return False

    # Parse to extract just the email part (handles "Name <email@domain.com>")
    _, addr = parseaddr(email)

    if not addr:
        return False

    # Basic regex for email validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, addr))

"""Email provider abstraction layer."""
import json
import logging
from typing import Optional, Dict

from .base import EmailProvider, EmailMessage, SendResult
from .gmail import GmailProvider
from .fastmail import FastmailProvider
from database.db import SessionLocal, Setting

__all__ = [
    "EmailProvider",
    "EmailMessage",
    "SendResult",
    "GmailProvider",
    "FastmailProvider",
    "get_active_provider",
    "get_provider_by_name",
]

logging.basicConfig(level=logging.INFO)

# Provider cache to avoid recreating instances
_provider_cache: Dict[str, EmailProvider] = {}


def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a setting from the database."""
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default
    finally:
        db.close()


def get_active_provider() -> EmailProvider:
    """Get the currently active email provider.

    Returns:
        EmailProvider instance for the active provider

    Raises:
        ValueError: If provider is unknown or not configured
    """
    provider_name = _get_setting("email_provider", "gmail")
    return get_provider_by_name(provider_name)


def get_provider_by_name(name: str, use_cache: bool = True) -> EmailProvider:
    """Get a specific provider by name.

    Args:
        name: Provider identifier ('gmail' or 'fastmail')
        use_cache: Whether to use cached provider instance (default: True)

    Returns:
        EmailProvider instance

    Raises:
        ValueError: If provider is unknown or not configured
    """
    # Check cache first
    if use_cache and name in _provider_cache:
        return _provider_cache[name]

    # Create provider instance
    provider: EmailProvider
    if name == "gmail":
        provider = GmailProvider()

    elif name == "fastmail":
        api_token = _get_setting("fastmail_api_key")
        account_id = _get_setting("fastmail_account_id")

        if not api_token:
            raise ValueError("Fastmail API key not configured")

        provider = FastmailProvider(api_token=api_token, account_id=account_id)

    else:
        raise ValueError(f"Unknown email provider: {name}")

    # Cache the provider
    if use_cache:
        _provider_cache[name] = provider

    return provider

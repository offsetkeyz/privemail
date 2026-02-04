"""Integration tests for email provider abstraction."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# Test provider factory
def test_get_provider_gmail_default():
    """Default provider should be Gmail."""
    with patch('clients.email_provider._get_setting', return_value='gmail'):
        import sys
        sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
        from clients.email_provider import get_active_provider, GmailProvider
        provider = get_active_provider()
        assert isinstance(provider, GmailProvider)
        assert provider.provider_name == "gmail"


def test_get_provider_fastmail():
    """Should return FastmailProvider when configured."""
    def mock_setting(key, default=None):
        settings = {
            'email_provider': 'fastmail',
            'fastmail_api_key': 'fmu1-test-key',
            'fastmail_account_id': 'u12345'
        }
        return settings.get(key, default)

    with patch('clients.email_provider._get_setting', side_effect=mock_setting):
        import sys
        sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
        from clients.email_provider import get_active_provider, FastmailProvider
        provider = get_active_provider()
        assert isinstance(provider, FastmailProvider)
        assert provider.provider_name == "fastmail"


def test_get_provider_fastmail_not_configured():
    """Should raise ValueError if Fastmail not configured."""
    def mock_setting(key, default=None):
        if key == 'email_provider':
            return 'fastmail'
        return None

    with patch('clients.email_provider._get_setting', side_effect=mock_setting):
        import sys
        sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
        from clients.email_provider import get_active_provider
        import clients.email_provider
        # Clear cache to avoid test pollution
        clients.email_provider._provider_cache.clear()
        with pytest.raises(ValueError, match="not configured"):
            get_active_provider()


# Test GmailProvider interface
@pytest.mark.asyncio
async def test_gmail_provider_interface():
    """GmailProvider should implement EmailProvider interface."""
    import sys
    sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
    from clients.email_provider import GmailProvider, EmailProvider

    provider = GmailProvider()
    assert isinstance(provider, EmailProvider)
    assert provider.provider_name == "gmail"


# Test FastmailProvider interface
@pytest.mark.asyncio
async def test_fastmail_provider_interface():
    """FastmailProvider should implement EmailProvider interface."""
    import sys
    sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
    from clients.email_provider import FastmailProvider, EmailProvider

    provider = FastmailProvider(api_token="test", account_id="u123")
    assert isinstance(provider, EmailProvider)
    assert provider.provider_name == "fastmail"


# Test email validation
def test_email_validation():
    """Test email address validation utility."""
    import sys
    sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
    from clients.email_provider import is_valid_email

    assert is_valid_email("user@example.com") is True
    assert is_valid_email("User Name <user@example.com>") is True
    assert is_valid_email("invalid-email") is False
    assert is_valid_email("@example.com") is False
    assert is_valid_email("") is False
    assert is_valid_email(None) is False


# Test provider caching
def test_provider_caching():
    """Test that providers are cached properly."""
    with patch('clients.email_provider._get_setting', return_value='gmail'):
        import sys
        sys.path.insert(0, '/home/offsetkeyz/projects/privemail-email-providers/src')
        from clients.email_provider import get_provider_by_name

        # Clear cache first
        import clients.email_provider
        clients.email_provider._provider_cache.clear()

        # Get provider twice
        provider1 = get_provider_by_name('gmail', use_cache=True)
        provider2 = get_provider_by_name('gmail', use_cache=True)

        # Should be the same instance
        assert provider1 is provider2

        # Get without cache
        provider3 = get_provider_by_name('gmail', use_cache=False)
        assert provider3 is not provider1

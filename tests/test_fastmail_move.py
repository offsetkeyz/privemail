"""Tests for Fastmail move/folder methods."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, 'src')

from clients.email_provider.fastmail import FastmailProvider
from clients.email_provider.base import MoveResult, Mailbox


@pytest.fixture
def provider():
    """Create FastmailProvider with mocked client."""
    return FastmailProvider(api_token="test-token", account_id="u123")


@pytest.mark.asyncio
async def test_get_mailboxes(provider):
    """get_mailboxes returns list of Mailbox objects."""
    # Create mock mailbox objects
    mock_inbox = MagicMock()
    mock_inbox.id = "M1"
    mock_inbox.name = "Inbox"
    mock_inbox.role = "inbox"

    mock_newsletters = MagicMock()
    mock_newsletters.id = "M2"
    mock_newsletters.name = "Newsletters"
    mock_newsletters.role = None

    # Setup query result
    mock_query_result = MagicMock()
    mock_query_result.ids = ["M1", "M2"]

    # Setup get result
    mock_get_result = MagicMock()
    mock_get_result.data = [mock_inbox, mock_newsletters]

    with patch.object(provider, '_get_client') as mock_client:
        # First call returns query result, second returns get result
        mock_client.return_value.request.side_effect = [mock_query_result, mock_get_result]
        with patch.object(provider, '_get_account_id', return_value="u123"):
            mailboxes = await provider.get_mailboxes()

    assert len(mailboxes) == 2
    assert isinstance(mailboxes[0], Mailbox)
    assert mailboxes[0].name == "Inbox"


@pytest.mark.asyncio
async def test_move_to_spam(provider):
    """move_to_spam moves email to Spam folder."""
    mock_result = MagicMock()
    mock_result.updated = {"email123": True}

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
        with patch.object(provider, '_get_account_id', return_value="u123"):
            with patch.object(provider, '_get_mailbox_id_by_role', return_value="SpamId"):
                result = await provider.move_to_spam("email123")

    assert result.success is True
    assert result.new_folder == "Spam"


@pytest.mark.asyncio
async def test_move_to_folder(provider):
    """move_to_folder moves email to specified folder."""
    mock_result = MagicMock()
    mock_result.updated = {"email123": True}

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
        with patch.object(provider, '_get_account_id', return_value="u123"):
            with patch.object(provider, '_get_mailbox_id_by_name', return_value="NewsId"):
                result = await provider.move_to_folder("email123", "Newsletters")

    assert result.success is True
    assert result.new_folder == "Newsletters"


@pytest.mark.asyncio
async def test_create_mailbox(provider):
    """create_mailbox creates new folder."""
    mock_result = MagicMock()
    mock_result.created = {"new": MagicMock(id="NewId")}

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
        with patch.object(provider, '_get_account_id', return_value="u123"):
            mailbox_id = await provider.create_mailbox("Receipts")

    assert mailbox_id == "NewId"

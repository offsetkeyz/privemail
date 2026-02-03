"""Tests for Gmail move/folder methods."""
import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, 'src')

from clients.email_provider.gmail import GmailProvider
from clients.email_provider.base import MoveResult, Mailbox


@pytest.fixture
def provider():
    """Create GmailProvider with mocked service."""
    return GmailProvider()


@pytest.mark.asyncio
async def test_get_mailboxes(provider):
    """get_mailboxes returns Gmail labels as Mailbox objects."""
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Newsletters', 'type': 'user'},
        ]
    }

    with patch.object(provider, '_get_service', return_value=mock_service):
        mailboxes = await provider.get_mailboxes()

    assert len(mailboxes) == 2
    assert isinstance(mailboxes[0], Mailbox)


@pytest.mark.asyncio
async def test_move_to_spam(provider):
    """move_to_spam adds SPAM label and removes INBOX."""
    mock_service = MagicMock()
    mock_service.users().messages().modify().execute.return_value = {'id': 'msg123'}

    with patch.object(provider, '_get_service', return_value=mock_service):
        result = await provider.move_to_spam("msg123")

    assert result.success is True
    assert result.new_folder == "Spam"


@pytest.mark.asyncio
async def test_move_to_folder(provider):
    """move_to_folder adds label and removes INBOX."""
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [{'id': 'Label_1', 'name': 'Newsletters'}]
    }
    mock_service.users().messages().modify().execute.return_value = {'id': 'msg123'}

    with patch.object(provider, '_get_service', return_value=mock_service):
        result = await provider.move_to_folder("msg123", "Newsletters")

    assert result.success is True
    assert result.new_folder == "Newsletters"


@pytest.mark.asyncio
async def test_create_mailbox(provider):
    """create_mailbox creates Gmail label."""
    mock_service = MagicMock()
    mock_service.users().labels().create().execute.return_value = {'id': 'Label_new'}

    with patch.object(provider, '_get_service', return_value=mock_service):
        label_id = await provider.create_mailbox("Receipts")

    assert label_id == "Label_new"


@pytest.mark.asyncio
async def test_create_filter_rule_not_supported(provider):
    """create_filter_rule returns None for Gmail."""
    from core.rule_generator import ProposedRule

    rule = ProposedRule(rule_type="domain", pattern="test.com", action="spam", evidence_count=3)
    result = await provider.create_filter_rule(rule)
    assert result is None

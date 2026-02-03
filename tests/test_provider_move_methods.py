"""Tests for provider move/folder methods."""
import pytest
from abc import ABC

import sys
sys.path.insert(0, 'src')

from clients.email_provider.base import EmailProvider
from core.rule_generator import ProposedRule


def test_email_provider_has_move_methods():
    """EmailProvider ABC should define move methods."""
    assert hasattr(EmailProvider, 'move_to_folder')
    assert hasattr(EmailProvider, 'move_to_spam')
    assert hasattr(EmailProvider, 'get_mailboxes')
    assert hasattr(EmailProvider, 'create_mailbox')


def test_email_provider_has_filter_methods():
    """EmailProvider ABC should define filter rule methods."""
    assert hasattr(EmailProvider, 'create_filter_rule')
    assert hasattr(EmailProvider, 'delete_filter_rule')


def test_move_result_dataclass():
    """MoveResult holds move operation results."""
    from clients.email_provider.base import MoveResult

    result = MoveResult(success=True, new_folder="Spam")
    assert result.success is True
    assert result.new_folder == "Spam"
    assert result.error is None


def test_mailbox_dataclass():
    """Mailbox holds folder info."""
    from clients.email_provider.base import Mailbox

    mailbox = Mailbox(id="M123", name="Newsletters", role=None)
    assert mailbox.id == "M123"
    assert mailbox.name == "Newsletters"

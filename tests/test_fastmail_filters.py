"""Tests for Fastmail filter rule creation."""
import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, 'src')

from clients.email_provider.fastmail import FastmailProvider
from core.rule_generator import ProposedRule


@pytest.fixture
def provider():
    return FastmailProvider(api_token="test-token", account_id="u123")


@pytest.mark.asyncio
async def test_create_filter_rule_spam(provider):
    """create_filter_rule creates spam filter."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="spammy.com",
        action="spam",
        evidence_count=4
    )

    rule_id = await provider.create_filter_rule(rule)
    assert rule_id is not None
    assert rule_id.startswith("privemail:")


@pytest.mark.asyncio
async def test_delete_filter_rule(provider):
    """delete_filter_rule removes filter."""
    result = await provider.delete_filter_rule("privemail:domain:test.com:spam")
    assert result is True

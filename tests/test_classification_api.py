"""Tests for classification API routes."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, 'src')


@pytest.fixture
def client():
    """Create test client with mocked dependencies."""
    from main import app
    return TestClient(app)


def test_classify_spam(client):
    """POST /api/emails/{id}/classify moves to spam."""
    mock_move_result = MagicMock()
    mock_move_result.success = True
    mock_move_result.new_folder = "Spam"
    mock_move_result.error = None

    mock_provider = MagicMock()
    mock_provider.move_to_spam = AsyncMock(return_value=mock_move_result)

    mock_email = MagicMock()
    mock_email.id = 1
    mock_email.message_id = "msg123"
    mock_email.sender = "spam@evil.com"
    mock_email.provider = "fastmail"

    with patch('routes.classification.get_active_provider', return_value=mock_provider):
        with patch('routes.classification.get_db') as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_email
            mock_get_db.return_value.__enter__.return_value = mock_session
            mock_get_db.return_value.__exit__.return_value = False

            response = client.post(
                "/api/emails/1/classify",
                json={"classification": "spam"}
            )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["moved_to"] == "Spam"


def test_classify_wanted(client):
    """POST /api/emails/{id}/classify as wanted records but doesn't move."""
    mock_email = MagicMock()
    mock_email.id = 1
    mock_email.message_id = "msg123"
    mock_email.sender = "friend@good.com"
    mock_email.provider = "gmail"

    with patch('routes.classification.get_active_provider'):
        with patch('routes.classification.get_db') as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_email
            mock_get_db.return_value.__enter__.return_value = mock_session
            mock_get_db.return_value.__exit__.return_value = False

            response = client.post(
                "/api/emails/1/classify",
                json={"classification": "wanted"}
            )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["moved_to"] is None

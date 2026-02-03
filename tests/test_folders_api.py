"""Tests for folders API routes."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, 'src')


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_get_folders(client):
    """GET /api/folders returns merged folder list."""
    mock_mailbox = MagicMock()
    mock_mailbox.name = "Newsletters"
    mock_mailbox.role = None

    mock_provider = MagicMock()
    mock_provider.get_mailboxes = AsyncMock(return_value=[mock_mailbox])

    with patch('routes.folders.get_active_provider', return_value=mock_provider):
        with patch('routes.folders.get_db') as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.order_by.return_value.all.return_value = []
            mock_get_db.return_value.__enter__.return_value = mock_session
            mock_get_db.return_value.__exit__.return_value = False

            response = client.get("/api/folders")

    assert response.status_code == 200
    assert "folders" in response.json()

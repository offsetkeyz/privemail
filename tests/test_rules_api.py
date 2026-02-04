"""Tests for rules API routes."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, 'src')


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_get_rules(client):
    """GET /api/rules returns suggested and applied rules."""
    mock_generator = MagicMock()
    mock_generator.get_suggested_rules.return_value = []

    with patch('routes.rules.RuleGenerator', return_value=mock_generator):
        with patch('routes.rules.get_db') as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = []
            mock_get_db.return_value.__enter__.return_value = mock_session
            mock_get_db.return_value.__exit__.return_value = False

            with patch('routes.rules._get_setting', return_value='fastmail'):
                response = client.get("/api/rules")

    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "rules_supported" in data

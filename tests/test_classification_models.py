"""Tests for email classification database models."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, 'src')

from database.db import Base, EmailClassification, EmailRule, UserFolder


@pytest.fixture
def db_session():
    """Create in-memory database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_email_classification_model(db_session):
    """EmailClassification stores classification data."""
    classification = EmailClassification(
        email_id=1,
        sender="test@example.com",
        sender_domain="example.com",
        classification="spam",
        provider="fastmail"
    )
    db_session.add(classification)
    db_session.commit()

    result = db_session.query(EmailClassification).first()
    assert result.sender == "test@example.com"
    assert result.classification == "spam"
    assert result.folder is None


def test_email_classification_with_folder(db_session):
    """EmailClassification stores folder for categorize action."""
    classification = EmailClassification(
        email_id=2,
        sender="news@substack.com",
        sender_domain="substack.com",
        classification="categorize",
        folder="Newsletters",
        provider="fastmail"
    )
    db_session.add(classification)
    db_session.commit()

    result = db_session.query(EmailClassification).first()
    assert result.classification == "categorize"
    assert result.folder == "Newsletters"


def test_email_rule_model(db_session):
    """EmailRule stores rule data."""
    rule = EmailRule(
        rule_type="domain",
        pattern="spam.com",
        action="spam"
    )
    db_session.add(rule)
    db_session.commit()

    result = db_session.query(EmailRule).first()
    assert result.rule_type == "domain"
    assert result.pattern == "spam.com"
    assert result.fastmail_rule_id is None
    assert result.dismissed is False


def test_email_rule_applied(db_session):
    """EmailRule tracks applied rules."""
    rule = EmailRule(
        rule_type="sender",
        pattern="news@substack.com",
        action="categorize",
        folder="Newsletters",
        fastmail_rule_id="Mf1234"
    )
    db_session.add(rule)
    db_session.commit()

    result = db_session.query(EmailRule).first()
    assert result.fastmail_rule_id == "Mf1234"


def test_user_folder_model(db_session):
    """UserFolder caches folder choices."""
    folder = UserFolder(
        folder_name="Newsletters",
        provider="fastmail",
        use_count=5
    )
    db_session.add(folder)
    db_session.commit()

    result = db_session.query(UserFolder).first()
    assert result.folder_name == "Newsletters"
    assert result.use_count == 5

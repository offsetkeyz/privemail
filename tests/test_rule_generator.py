"""Tests for rule generator logic."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, 'src')

from database.db import Base, EmailClassification
from core.rule_generator import RuleGenerator, ProposedRule


@pytest.fixture
def db_session():
    """Create in-memory database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_proposed_rule_dataclass():
    """ProposedRule holds rule data."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="spam.com",
        action="spam",
        evidence_count=5
    )
    assert rule.rule_type == "domain"
    assert rule.folder is None


def test_generate_sieve_spam_domain():
    """Generate sieve code for domain spam rule."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="marketingblast.com",
        action="spam",
        evidence_count=4
    )
    sieve = RuleGenerator.generate_sieve(rule)
    assert 'address :domain "from" "marketingblast.com"' in sieve
    assert 'fileinto "Spam"' in sieve
    assert "stop;" in sieve


def test_generate_sieve_spam_sender():
    """Generate sieve code for sender spam rule."""
    rule = ProposedRule(
        rule_type="sender",
        pattern="spammer@evil.com",
        action="spam",
        evidence_count=2
    )
    sieve = RuleGenerator.generate_sieve(rule)
    assert 'address :is "from" "spammer@evil.com"' in sieve
    assert 'fileinto "Spam"' in sieve


def test_generate_sieve_categorize():
    """Generate sieve code for categorize rule."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="substack.com",
        action="categorize",
        folder="Newsletters",
        evidence_count=3
    )
    sieve = RuleGenerator.generate_sieve(rule)
    assert 'address :domain "from" "substack.com"' in sieve
    assert 'fileinto "Newsletters"' in sieve


def test_generate_sieve_wanted():
    """Generate sieve code for wanted rule."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="important.com",
        action="wanted",
        evidence_count=3
    )
    sieve = RuleGenerator.generate_sieve(rule)
    assert "keep;" in sieve


def test_detect_spam_domains(db_session):
    """Detect domains with 3+ spam classifications."""
    # Add 4 spam emails from same domain
    for i in range(4):
        db_session.add(EmailClassification(
            email_id=i,
            sender=f"user{i}@spammy.com",
            sender_domain="spammy.com",
            classification="spam",
            provider="fastmail"
        ))
    # Add 2 spam from another domain (below threshold)
    for i in range(2):
        db_session.add(EmailClassification(
            email_id=10+i,
            sender=f"user{i}@other.com",
            sender_domain="other.com",
            classification="spam",
            provider="fastmail"
        ))
    db_session.commit()

    generator = RuleGenerator(db_session, domain_threshold=3)
    rules = generator.get_suggested_rules()

    spam_domains = [r for r in rules if r.rule_type == "domain" and r.action == "spam"]
    assert len(spam_domains) == 1
    assert spam_domains[0].pattern == "spammy.com"
    assert spam_domains[0].evidence_count == 4


def test_detect_categorize_domains(db_session):
    """Detect domains with 3+ categorize to same folder."""
    for i in range(3):
        db_session.add(EmailClassification(
            email_id=i,
            sender=f"news{i}@substack.com",
            sender_domain="substack.com",
            classification="categorize",
            folder="Newsletters",
            provider="fastmail"
        ))
    db_session.commit()

    generator = RuleGenerator(db_session, domain_threshold=3)
    rules = generator.get_suggested_rules()

    cat_rules = [r for r in rules if r.action == "categorize"]
    assert len(cat_rules) == 1
    assert cat_rules[0].pattern == "substack.com"
    assert cat_rules[0].folder == "Newsletters"

# Email Classification & Rules Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add email classification (spam/wanted/categorize) with quick action buttons and Fastmail sieve rule generation.

**Architecture:** New SQLAlchemy models for classifications and rules. Extend EmailProvider ABC with folder/move methods. New RuleGenerator in core module ported from fastmail_sorter. API routes for classification actions and rule management.

**Tech Stack:** SQLAlchemy (existing), FastAPI (existing), jmapc (existing for Fastmail)

---

## Task 1: Database Models for Classification

**Files:**
- Modify: `src/database/db.py`
- Test: `tests/test_classification_models.py`

**Step 1: Write the failing test**

Create `tests/test_classification_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_classification_models.py -v`

Expected: FAIL with `ImportError: cannot import name 'EmailClassification'`

**Step 3: Add models to db.py**

Add after the `Setting` class in `src/database/db.py`:

```python
class EmailClassification(Base):
    __tablename__ = "email_classifications"
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False)
    sender = Column(String, nullable=False, index=True)
    sender_domain = Column(String, nullable=False, index=True)
    classification = Column(String, nullable=False)  # 'spam', 'wanted', 'categorize'
    folder = Column(String, nullable=True)  # target folder for 'categorize'
    provider = Column(String, nullable=False)  # 'gmail' or 'fastmail'
    created_at = Column(String, default=lambda: datetime.now().isoformat())


class EmailRule(Base):
    __tablename__ = "email_rules"
    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String, nullable=False)  # 'sender' or 'domain'
    pattern = Column(String, nullable=False)
    action = Column(String, nullable=False)  # 'spam', 'wanted', 'categorize'
    folder = Column(String, nullable=True)  # for 'categorize' rules
    fastmail_rule_id = Column(String, nullable=True)  # NULL if not applied
    dismissed = Column(Boolean, default=False)
    created_at = Column(String, default=lambda: datetime.now().isoformat())
    applied_at = Column(String, nullable=True)


class UserFolder(Base):
    __tablename__ = "user_folders"
    folder_name = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    use_count = Column(Integer, default=1)
    last_used = Column(String, default=lambda: datetime.now().isoformat())
```

Also add `from datetime import datetime` at the top of the file.

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_classification_models.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/database/db.py tests/test_classification_models.py
git commit -m "feat: add database models for email classification and rules"
```

---

## Task 2: RuleGenerator Core Module

**Files:**
- Create: `src/core/rule_generator.py`
- Test: `tests/test_rule_generator.py`

**Step 1: Write the failing test**

Create `tests/test_rule_generator.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_rule_generator.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'core.rule_generator'`

**Step 3: Create rule_generator.py**

Create `src/core/rule_generator.py`:

```python
"""Rule generator for creating Fastmail sieve rules from classifications."""
from dataclasses import dataclass
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.db import EmailClassification


@dataclass
class ProposedRule:
    """A proposed email filter rule."""
    rule_type: str  # 'sender' or 'domain'
    pattern: str
    action: str  # 'spam', 'wanted', 'categorize'
    evidence_count: int
    folder: Optional[str] = None


class RuleGenerator:
    """Generates filter rules from classification history."""

    def __init__(
        self,
        db_session: Session,
        domain_threshold: int = 3,
        sender_threshold: int = 2,
    ):
        self.db = db_session
        self.domain_threshold = domain_threshold
        self.sender_threshold = sender_threshold

    def get_suggested_rules(self) -> List[ProposedRule]:
        """Generate all proposed rules from classification data."""
        rules = []
        rules.extend(self._detect_spam_domains())
        rules.extend(self._detect_spam_senders())
        rules.extend(self._detect_wanted_domains())
        rules.extend(self._detect_wanted_senders())
        rules.extend(self._detect_categorize_domains())
        rules.extend(self._detect_categorize_senders())
        return rules

    def _detect_spam_domains(self) -> List[ProposedRule]:
        """Find domains with multiple spam classifications."""
        results = (
            self.db.query(
                EmailClassification.sender_domain,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'spam')
            .group_by(EmailClassification.sender_domain)
            .having(func.count() >= self.domain_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="domain",
                pattern=row.sender_domain,
                action="spam",
                evidence_count=row.count
            )
            for row in results
        ]

    def _detect_spam_senders(self) -> List[ProposedRule]:
        """Find senders with multiple spam classifications."""
        results = (
            self.db.query(
                EmailClassification.sender,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'spam')
            .group_by(EmailClassification.sender)
            .having(func.count() >= self.sender_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="sender",
                pattern=row.sender,
                action="spam",
                evidence_count=row.count
            )
            for row in results
        ]

    def _detect_wanted_domains(self) -> List[ProposedRule]:
        """Find domains with multiple wanted classifications."""
        results = (
            self.db.query(
                EmailClassification.sender_domain,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'wanted')
            .group_by(EmailClassification.sender_domain)
            .having(func.count() >= self.domain_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="domain",
                pattern=row.sender_domain,
                action="wanted",
                evidence_count=row.count
            )
            for row in results
        ]

    def _detect_wanted_senders(self) -> List[ProposedRule]:
        """Find senders with multiple wanted classifications."""
        results = (
            self.db.query(
                EmailClassification.sender,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'wanted')
            .group_by(EmailClassification.sender)
            .having(func.count() >= self.sender_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="sender",
                pattern=row.sender,
                action="wanted",
                evidence_count=row.count
            )
            for row in results
        ]

    def _detect_categorize_domains(self) -> List[ProposedRule]:
        """Find domains with multiple categorize to same folder."""
        results = (
            self.db.query(
                EmailClassification.sender_domain,
                EmailClassification.folder,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'categorize')
            .filter(EmailClassification.folder.isnot(None))
            .group_by(EmailClassification.sender_domain, EmailClassification.folder)
            .having(func.count() >= self.domain_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="domain",
                pattern=row.sender_domain,
                action="categorize",
                folder=row.folder,
                evidence_count=row.count
            )
            for row in results
        ]

    def _detect_categorize_senders(self) -> List[ProposedRule]:
        """Find senders with multiple categorize to same folder."""
        results = (
            self.db.query(
                EmailClassification.sender,
                EmailClassification.folder,
                func.count().label('count')
            )
            .filter(EmailClassification.classification == 'categorize')
            .filter(EmailClassification.folder.isnot(None))
            .group_by(EmailClassification.sender, EmailClassification.folder)
            .having(func.count() >= self.sender_threshold)
            .all()
        )
        return [
            ProposedRule(
                rule_type="sender",
                pattern=row.sender,
                action="categorize",
                folder=row.folder,
                evidence_count=row.count
            )
            for row in results
        ]

    @staticmethod
    def generate_sieve(rule: ProposedRule) -> str:
        """Generate sieve script for a rule."""
        # Build condition
        if rule.rule_type == "sender":
            condition = f'address :is "from" "{rule.pattern}"'
        elif rule.rule_type == "domain":
            condition = f'address :domain "from" "{rule.pattern}"'
        else:
            return ""

        # Build action
        if rule.action == "spam":
            action = 'fileinto "Spam"; stop;'
        elif rule.action == "categorize" and rule.folder:
            action = f'fileinto "{rule.folder}"; stop;'
        elif rule.action == "wanted":
            action = "keep;"
        else:
            return ""

        return f'if {condition} {{ {action} }}'
```

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_rule_generator.py -v`

Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add src/core/rule_generator.py tests/test_rule_generator.py
git commit -m "feat: add rule generator for sieve code from classifications"
```

---

## Task 3: Provider Move/Folder Methods - Base Class

**Files:**
- Modify: `src/clients/email_provider/base.py`
- Test: `tests/test_provider_move_methods.py`

**Step 1: Write the failing test**

Create `tests/test_provider_move_methods.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_provider_move_methods.py -v`

Expected: FAIL with `AssertionError` (methods not found)

**Step 3: Add methods to base.py**

Update `src/clients/email_provider/base.py`:

```python
"""Abstract base class for email providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.rule_generator import ProposedRule


@dataclass
class EmailMessage:
    """Standardized email message from any provider."""
    message_id: str
    sender: str
    subject: str
    body_text: str
    received_at: Optional[datetime] = None


@dataclass
class SendResult:
    """Result of a send or create_draft operation."""
    success: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class MoveResult:
    """Result of a move operation."""
    success: bool
    new_folder: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Mailbox:
    """Represents an email folder/mailbox."""
    id: str
    name: str
    role: Optional[str] = None  # 'inbox', 'spam', 'drafts', etc.


class EmailProvider(ABC):
    """Abstract interface for email providers.

    All email providers (Gmail, Fastmail, etc.) must implement this interface.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier (e.g., 'gmail', 'fastmail')."""
        pass

    @abstractmethod
    async def fetch_unread_messages(self, limit: int = 10) -> List[EmailMessage]:
        """Fetch unread messages from inbox."""
        pass

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Send an email."""
        pass

    @abstractmethod
    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Create a draft in the provider."""
        pass

    @abstractmethod
    async def get_contacts(self) -> List[Dict[str, Any]]:
        """Fetch contacts from provider."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify credentials are valid."""
        pass

    # --- New methods for classification feature ---

    @abstractmethod
    async def move_to_folder(self, email_id: str, folder: str) -> MoveResult:
        """Move an email to the specified folder.

        Args:
            email_id: Provider-specific message ID
            folder: Target folder name

        Returns:
            MoveResult indicating success/failure
        """
        pass

    @abstractmethod
    async def move_to_spam(self, email_id: str) -> MoveResult:
        """Move an email to the Spam folder.

        Args:
            email_id: Provider-specific message ID

        Returns:
            MoveResult indicating success/failure
        """
        pass

    @abstractmethod
    async def get_mailboxes(self) -> List[Mailbox]:
        """List all mailboxes/folders.

        Returns:
            List of Mailbox objects
        """
        pass

    @abstractmethod
    async def create_mailbox(self, name: str) -> Optional[str]:
        """Create a new mailbox/folder.

        Args:
            name: Name for the new folder

        Returns:
            The new mailbox ID, or None if failed
        """
        pass

    async def create_filter_rule(self, rule: "ProposedRule") -> Optional[str]:
        """Create a filter rule in the provider.

        Args:
            rule: The rule to create

        Returns:
            The rule ID if created, None if not supported

        Note: Default implementation returns None (not supported).
        Override in providers that support filter rules (e.g., Fastmail).
        """
        return None

    async def delete_filter_rule(self, rule_id: str) -> bool:
        """Delete a filter rule from the provider.

        Args:
            rule_id: The provider-specific rule ID

        Returns:
            True if deleted, False if not supported or failed

        Note: Default implementation returns False (not supported).
        Override in providers that support filter rules.
        """
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_provider_move_methods.py -v`

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/clients/email_provider/base.py tests/test_provider_move_methods.py
git commit -m "feat: add move/folder/filter methods to EmailProvider ABC"
```

---

## Task 4: Fastmail Provider - Move/Folder Methods

**Files:**
- Modify: `src/clients/email_provider/fastmail.py`
- Test: `tests/test_fastmail_move.py`

**Step 1: Write the failing test**

Create `tests/test_fastmail_move.py`:

```python
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
    mock_result = MagicMock()
    mock_result.data = [
        MagicMock(id="M1", name="Inbox", role="inbox"),
        MagicMock(id="M2", name="Newsletters", role=None),
    ]

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_fastmail_move.py -v`

Expected: FAIL with `AttributeError: 'FastmailProvider' object has no attribute 'get_mailboxes'`

**Step 3: Add methods to fastmail.py**

Add these methods to the `FastmailProvider` class in `src/clients/email_provider/fastmail.py`:

```python
    # Add these imports at top of file
    from jmapc.methods import MailboxGet, MailboxSet

    # Add to class after existing methods:

    async def _get_mailbox_id_by_role(self, role: str) -> Optional[str]:
        """Get mailbox ID by role (inbox, spam, drafts, etc.)."""
        try:
            client = self._get_client()
            account_id = self._get_account_id()

            query = MailboxQuery(filter={"role": role})
            query.account_id = account_id
            result = client.request(query)

            if result and result.ids:
                return result.ids[0]
            return None
        except Exception as e:
            logging.error(f"Error getting mailbox by role {role}: {e}")
            return None

    async def _get_mailbox_id_by_name(self, name: str) -> Optional[str]:
        """Get mailbox ID by name."""
        try:
            client = self._get_client()
            account_id = self._get_account_id()

            query = MailboxQuery(filter={"name": name})
            query.account_id = account_id
            result = client.request(query)

            if result and result.ids:
                return result.ids[0]
            return None
        except Exception as e:
            logging.error(f"Error getting mailbox by name {name}: {e}")
            return None

    async def get_mailboxes(self) -> List["Mailbox"]:
        """List all mailboxes/folders."""
        from .base import Mailbox

        try:
            client = self._get_client()
            account_id = self._get_account_id()

            mailbox_get = MailboxGet()
            mailbox_get.account_id = account_id
            result = client.request(mailbox_get)

            mailboxes = []
            for mb in result.data:
                mailboxes.append(Mailbox(
                    id=mb.id,
                    name=mb.name,
                    role=mb.role
                ))
            return mailboxes
        except Exception as e:
            logging.error(f"Error getting mailboxes: {e}")
            return []

    async def move_to_spam(self, email_id: str) -> "MoveResult":
        """Move email to Spam folder."""
        from .base import MoveResult

        spam_id = await self._get_mailbox_id_by_role("junk")
        if not spam_id:
            # Try by name as fallback
            spam_id = await self._get_mailbox_id_by_name("Spam")

        if not spam_id:
            return MoveResult(success=False, error="Could not find Spam folder")

        try:
            client = self._get_client()
            account_id = self._get_account_id()

            email_set = EmailSet(
                update={
                    email_id: {"mailboxIds": {spam_id: True}}
                }
            )
            email_set.account_id = account_id
            result = client.request(email_set)

            if result.updated and email_id in result.updated:
                return MoveResult(success=True, new_folder="Spam")
            return MoveResult(success=False, error="Move failed")
        except Exception as e:
            logging.error(f"Error moving to spam: {e}")
            return MoveResult(success=False, error=str(e))

    async def move_to_folder(self, email_id: str, folder: str) -> "MoveResult":
        """Move email to specified folder."""
        from .base import MoveResult

        folder_id = await self._get_mailbox_id_by_name(folder)
        if not folder_id:
            return MoveResult(success=False, error=f"Folder '{folder}' not found")

        try:
            client = self._get_client()
            account_id = self._get_account_id()

            email_set = EmailSet(
                update={
                    email_id: {"mailboxIds": {folder_id: True}}
                }
            )
            email_set.account_id = account_id
            result = client.request(email_set)

            if result.updated and email_id in result.updated:
                return MoveResult(success=True, new_folder=folder)
            return MoveResult(success=False, error="Move failed")
        except Exception as e:
            logging.error(f"Error moving to folder: {e}")
            return MoveResult(success=False, error=str(e))

    async def create_mailbox(self, name: str) -> Optional[str]:
        """Create a new mailbox/folder."""
        try:
            client = self._get_client()
            account_id = self._get_account_id()

            mailbox_set = MailboxSet(
                create={"new": Mailbox(name=name)}
            )
            mailbox_set.account_id = account_id
            result = client.request(mailbox_set)

            if result.created and "new" in result.created:
                return result.created["new"].id
            return None
        except Exception as e:
            logging.error(f"Error creating mailbox: {e}")
            return None
```

Also add the import at the top:
```python
from jmapc.methods import MailboxGet, MailboxSet
```

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_fastmail_move.py -v`

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/clients/email_provider/fastmail.py tests/test_fastmail_move.py
git commit -m "feat: add move/folder methods to FastmailProvider"
```

---

## Task 5: Gmail Provider - Move/Folder Methods (Stubs)

**Files:**
- Modify: `src/clients/email_provider/gmail.py`
- Test: `tests/test_gmail_move.py`

**Step 1: Write the failing test**

Create `tests/test_gmail_move.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_gmail_move.py -v`

Expected: FAIL with `AttributeError`

**Step 3: Add methods to gmail.py**

Add these methods to the `GmailProvider` class in `src/clients/email_provider/gmail.py`:

```python
    # Add these imports at top:
    from .base import MoveResult, Mailbox

    # Add to class after existing methods:

    async def get_mailboxes(self) -> List[Mailbox]:
        """List Gmail labels as mailboxes."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return []

        try:
            result = await asyncio.to_thread(
                lambda: service.users().labels().list(userId='me').execute()
            )
            labels = result.get('labels', [])

            mailboxes = []
            for label in labels:
                role = None
                if label['id'] in ('INBOX', 'SPAM', 'TRASH', 'DRAFT', 'SENT'):
                    role = label['id'].lower()
                mailboxes.append(Mailbox(
                    id=label['id'],
                    name=label['name'],
                    role=role
                ))
            return mailboxes
        except Exception as e:
            logging.error(f"Error getting Gmail labels: {e}")
            return []

    async def move_to_spam(self, email_id: str) -> MoveResult:
        """Move email to Spam by modifying labels."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return MoveResult(success=False, error="Gmail service unavailable")

        try:
            await asyncio.to_thread(
                lambda: service.users().messages().modify(
                    userId='me',
                    id=email_id,
                    body={'addLabelIds': ['SPAM'], 'removeLabelIds': ['INBOX']}
                ).execute()
            )
            return MoveResult(success=True, new_folder="Spam")
        except Exception as e:
            logging.error(f"Error moving to spam: {e}")
            return MoveResult(success=False, error=str(e))

    async def move_to_folder(self, email_id: str, folder: str) -> MoveResult:
        """Move email to folder by adding label."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return MoveResult(success=False, error="Gmail service unavailable")

        try:
            # Find label ID by name
            labels_result = await asyncio.to_thread(
                lambda: service.users().labels().list(userId='me').execute()
            )
            label_id = None
            for label in labels_result.get('labels', []):
                if label['name'] == folder:
                    label_id = label['id']
                    break

            if not label_id:
                return MoveResult(success=False, error=f"Label '{folder}' not found")

            await asyncio.to_thread(
                lambda: service.users().messages().modify(
                    userId='me',
                    id=email_id,
                    body={'addLabelIds': [label_id], 'removeLabelIds': ['INBOX']}
                ).execute()
            )
            return MoveResult(success=True, new_folder=folder)
        except Exception as e:
            logging.error(f"Error moving to folder: {e}")
            return MoveResult(success=False, error=str(e))

    async def create_mailbox(self, name: str) -> Optional[str]:
        """Create a Gmail label."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return None

        try:
            result = await asyncio.to_thread(
                lambda: service.users().labels().create(
                    userId='me',
                    body={'name': name, 'labelListVisibility': 'labelShow'}
                ).execute()
            )
            return result.get('id')
        except Exception as e:
            logging.error(f"Error creating label: {e}")
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_gmail_move.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/clients/email_provider/gmail.py tests/test_gmail_move.py
git commit -m "feat: add move/folder methods to GmailProvider"
```

---

## Task 6: Classification API Route

**Files:**
- Create: `src/routes/classification.py`
- Modify: `src/main.py` (add router)
- Test: `tests/test_classification_api.py`

**Step 1: Write the failing test**

Create `tests/test_classification_api.py`:

```python
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
    mock_provider = MagicMock()
    mock_provider.move_to_spam = AsyncMock(return_value=MagicMock(
        success=True, new_folder="Spam", error=None
    ))

    mock_email = MagicMock()
    mock_email.id = 1
    mock_email.message_id = "msg123"
    mock_email.sender = "spam@evil.com"
    mock_email.provider = "fastmail"

    with patch('routes.classification.get_active_provider', return_value=mock_provider):
        with patch('routes.classification.get_db') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_email
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.post(
                "/api/emails/1/classify",
                json={"classification": "spam"}
            )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["moved_to"] == "Spam"


def test_classify_categorize(client):
    """POST /api/emails/{id}/classify with folder categorizes."""
    mock_provider = MagicMock()
    mock_provider.move_to_folder = AsyncMock(return_value=MagicMock(
        success=True, new_folder="Newsletters", error=None
    ))

    mock_email = MagicMock()
    mock_email.id = 1
    mock_email.message_id = "msg123"
    mock_email.sender = "news@substack.com"
    mock_email.provider = "fastmail"

    with patch('routes.classification.get_active_provider', return_value=mock_provider):
        with patch('routes.classification.get_db') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_email
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.post(
                "/api/emails/1/classify",
                json={"classification": "categorize", "folder": "Newsletters"}
            )

    assert response.status_code == 200
    assert response.json()["moved_to"] == "Newsletters"


def test_classify_wanted(client):
    """POST /api/emails/{id}/classify as wanted records but doesn't move."""
    mock_email = MagicMock()
    mock_email.id = 1
    mock_email.message_id = "msg123"
    mock_email.sender = "friend@good.com"
    mock_email.provider = "gmail"

    with patch('routes.classification.get_active_provider') as mock_get:
        with patch('routes.classification.get_db') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = mock_email
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.post(
                "/api/emails/1/classify",
                json={"classification": "wanted"}
            )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["moved_to"] is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_classification_api.py -v`

Expected: FAIL (route not found or import error)

**Step 3: Create classification.py route**

Create `src/routes/classification.py`:

```python
"""Email classification API routes."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from database.db import get_db, Email, EmailClassification, UserFolder
from clients.email_provider import get_active_provider

router = APIRouter(
    prefix="/emails",
    tags=["Classification"],
)


class ClassifyRequest(BaseModel):
    classification: str  # 'spam', 'wanted', 'categorize'
    folder: Optional[str] = None


class ClassifyResponse(BaseModel):
    success: bool
    moved_to: Optional[str] = None
    error: Optional[str] = None


def _extract_domain(sender: str) -> str:
    """Extract domain from sender email."""
    # Handle "Name <email@domain.com>" format
    if '<' in sender and '>' in sender:
        sender = sender.split('<')[1].split('>')[0]
    if '@' in sender:
        return sender.split('@')[1].lower()
    return sender.lower()


@router.post("/{email_id}/classify", response_model=ClassifyResponse)
async def classify_email(
    email_id: int,
    request: ClassifyRequest,
    db: Session = Depends(get_db)
):
    """Classify an email and optionally move it."""
    # Validate classification
    if request.classification not in ('spam', 'wanted', 'categorize'):
        raise HTTPException(status_code=400, detail="Invalid classification")

    if request.classification == 'categorize' and not request.folder:
        raise HTTPException(status_code=400, detail="Folder required for categorize")

    # Get email from database
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    provider = get_active_provider()
    moved_to = None

    try:
        # Perform move action based on classification
        if request.classification == 'spam':
            result = await provider.move_to_spam(email.message_id)
            if result.success:
                moved_to = result.new_folder
            else:
                return ClassifyResponse(success=False, error=result.error)

        elif request.classification == 'categorize':
            result = await provider.move_to_folder(email.message_id, request.folder)
            if result.success:
                moved_to = result.new_folder
                # Record folder usage
                _record_folder_use(db, request.folder, email.provider)
            else:
                return ClassifyResponse(success=False, error=result.error)

        # 'wanted' doesn't move the email

        # Record classification
        classification = EmailClassification(
            email_id=email.id,
            sender=email.sender,
            sender_domain=_extract_domain(email.sender),
            classification=request.classification,
            folder=request.folder,
            provider=email.provider
        )
        db.add(classification)
        db.commit()

        return ClassifyResponse(success=True, moved_to=moved_to)

    except Exception as e:
        logging.error(f"Classification error: {e}")
        return ClassifyResponse(success=False, error=str(e))


def _record_folder_use(db: Session, folder_name: str, provider: str):
    """Record or update folder usage."""
    existing = db.query(UserFolder).filter(
        UserFolder.folder_name == folder_name
    ).first()

    if existing:
        existing.use_count += 1
    else:
        db.add(UserFolder(
            folder_name=folder_name,
            provider=provider,
            use_count=1
        ))
```

**Step 4: Add router to main.py**

In `src/main.py`, add the import and include the router:

```python
from routes.classification import router as classification_router
# ... existing routers ...
app.include_router(classification_router, prefix="/api")
```

**Step 5: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_classification_api.py -v`

Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add src/routes/classification.py src/main.py tests/test_classification_api.py
git commit -m "feat: add email classification API endpoint"
```

---

## Task 7: Folders API Route

**Files:**
- Create: `src/routes/folders.py`
- Modify: `src/main.py` (add router)
- Test: `tests/test_folders_api.py`

**Step 1: Write the failing test**

Create `tests/test_folders_api.py`:

```python
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
    mock_provider = MagicMock()
    mock_provider.get_mailboxes = AsyncMock(return_value=[
        MagicMock(id="M1", name="Inbox", role="inbox"),
        MagicMock(id="M2", name="Newsletters", role=None),
    ])

    with patch('routes.folders.get_active_provider', return_value=mock_provider):
        with patch('routes.folders.get_db') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.order_by.return_value.all.return_value = [
                MagicMock(folder_name="Newsletters", use_count=5),
                MagicMock(folder_name="Receipts", use_count=2),
            ]
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.get("/api/folders")

    assert response.status_code == 200
    folders = response.json()["folders"]
    assert len(folders) >= 2


def test_create_folder(client):
    """POST /api/folders creates new folder."""
    mock_provider = MagicMock()
    mock_provider.create_mailbox = AsyncMock(return_value="NewId")
    mock_provider.provider_name = "fastmail"

    with patch('routes.folders.get_active_provider', return_value=mock_provider):
        with patch('routes.folders.get_db') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.post(
                "/api/folders",
                json={"name": "Receipts"}
            )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["folder"] == "Receipts"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_folders_api.py -v`

Expected: FAIL

**Step 3: Create folders.py route**

Create `src/routes/folders.py`:

```python
"""Folder management API routes."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.db import get_db, UserFolder
from clients.email_provider import get_active_provider

router = APIRouter(
    prefix="/folders",
    tags=["Folders"],
)


class FolderInfo(BaseModel):
    name: str
    use_count: int = 0
    from_provider: bool = False


class FoldersResponse(BaseModel):
    folders: List[FolderInfo]


class CreateFolderRequest(BaseModel):
    name: str


class CreateFolderResponse(BaseModel):
    success: bool
    folder: Optional[str] = None
    error: Optional[str] = None


@router.get("/", response_model=FoldersResponse)
async def get_folders(db: Session = Depends(get_db)):
    """Get list of folders, merged from provider and local cache."""
    provider = get_active_provider()

    # Get folders from provider
    provider_mailboxes = await provider.get_mailboxes()
    provider_names = {mb.name for mb in provider_mailboxes}

    # Get cached folder usage
    cached = db.query(UserFolder).order_by(desc(UserFolder.use_count)).all()
    cached_map = {f.folder_name: f.use_count for f in cached}

    # Merge: start with cached (sorted by use), add provider-only
    folders = []
    seen = set()

    # Add cached folders first (sorted by usage)
    for folder in cached:
        folders.append(FolderInfo(
            name=folder.folder_name,
            use_count=folder.use_count,
            from_provider=folder.folder_name in provider_names
        ))
        seen.add(folder.folder_name)

    # Add provider folders not in cache
    for mb in provider_mailboxes:
        if mb.name not in seen and mb.role not in ('inbox', 'spam', 'drafts', 'sent', 'trash'):
            folders.append(FolderInfo(
                name=mb.name,
                use_count=0,
                from_provider=True
            ))

    return FoldersResponse(folders=folders)


@router.post("/", response_model=CreateFolderResponse)
async def create_folder(
    request: CreateFolderRequest,
    db: Session = Depends(get_db)
):
    """Create a new folder in the email provider."""
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Folder name required")

    provider = get_active_provider()

    try:
        mailbox_id = await provider.create_mailbox(request.name)
        if mailbox_id:
            # Cache the folder
            db.add(UserFolder(
                folder_name=request.name,
                provider=provider.provider_name,
                use_count=1
            ))
            db.commit()
            return CreateFolderResponse(success=True, folder=request.name)
        else:
            return CreateFolderResponse(success=False, error="Failed to create folder")
    except Exception as e:
        logging.error(f"Error creating folder: {e}")
        return CreateFolderResponse(success=False, error=str(e))
```

**Step 4: Add router to main.py**

In `src/main.py`:

```python
from routes.folders import router as folders_router
# ...
app.include_router(folders_router, prefix="/api")
```

**Step 5: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_folders_api.py -v`

Expected: All 2 tests PASS

**Step 6: Commit**

```bash
git add src/routes/folders.py src/main.py tests/test_folders_api.py
git commit -m "feat: add folders API endpoints"
```

---

## Task 8: Rules API Route

**Files:**
- Create: `src/routes/rules.py`
- Modify: `src/main.py` (add router)
- Test: `tests/test_rules_api.py`

**Step 1: Write the failing test**

Create `tests/test_rules_api.py`:

```python
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
    mock_generator.get_suggested_rules.return_value = [
        MagicMock(rule_type="domain", pattern="spam.com", action="spam", evidence_count=4, folder=None)
    ]

    with patch('routes.rules.RuleGenerator', return_value=mock_generator):
        with patch('routes.rules.get_db') as mock_db:
            mock_session = MagicMock()
            # No applied rules
            mock_session.query.return_value.filter.return_value.all.return_value = []
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            with patch('routes.rules._get_setting', return_value='fastmail'):
                response = client.get("/api/rules")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "fastmail"
    assert data["rules_supported"] is True
    assert len(data["suggested"]) == 1


def test_get_rules_gmail_not_supported(client):
    """GET /api/rules shows rules_supported=false for Gmail."""
    with patch('routes.rules.RuleGenerator') as mock_gen:
        mock_gen.return_value.get_suggested_rules.return_value = []
        with patch('routes.rules.get_db') as mock_db:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = []
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            with patch('routes.rules._get_setting', return_value='gmail'):
                response = client.get("/api/rules")

    assert response.status_code == 200
    assert response.json()["rules_supported"] is False


def test_get_sieve_code(client):
    """GET /api/rules/{id}/sieve returns sieve code."""
    mock_rule = MagicMock()
    mock_rule.rule_type = "domain"
    mock_rule.pattern = "spam.com"
    mock_rule.action = "spam"
    mock_rule.folder = None

    with patch('routes.rules.get_db') as mock_db:
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_rule
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        response = client.get("/api/rules/1/sieve")

    assert response.status_code == 200
    assert 'fileinto "Spam"' in response.json()["sieve"]


def test_dismiss_rule(client):
    """POST /api/rules/{id}/dismiss marks rule as dismissed."""
    mock_rule = MagicMock()
    mock_rule.dismissed = False

    with patch('routes.rules.get_db') as mock_db:
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_rule
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        response = client.post("/api/rules/1/dismiss")

    assert response.status_code == 200
    assert response.json()["success"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_rules_api.py -v`

Expected: FAIL

**Step 3: Create rules.py route**

Create `src/routes/rules.py`:

```python
"""Email rules API routes."""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from database.db import get_db, EmailRule, Setting
from core.rule_generator import RuleGenerator, ProposedRule
from clients.email_provider import get_active_provider

router = APIRouter(
    prefix="/rules",
    tags=["Rules"],
)


def _get_setting(db: Session, key: str) -> Optional[str]:
    """Get a setting from database."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else None


class SuggestedRule(BaseModel):
    id: Optional[int] = None
    rule_type: str
    pattern: str
    action: str
    folder: Optional[str] = None
    evidence_count: int


class AppliedRule(BaseModel):
    id: int
    rule_type: str
    pattern: str
    action: str
    folder: Optional[str] = None
    applied_at: Optional[str] = None


class RulesResponse(BaseModel):
    suggested: List[SuggestedRule]
    applied: List[AppliedRule]
    provider: str
    rules_supported: bool


class SieveResponse(BaseModel):
    sieve: str


class SuccessResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    fastmail_rule_id: Optional[str] = None


@router.get("/", response_model=RulesResponse)
async def get_rules(db: Session = Depends(get_db)):
    """Get suggested and applied rules."""
    provider_name = _get_setting(db, "email_provider") or "gmail"
    rules_supported = provider_name == "fastmail"

    # Get suggested rules from generator
    generator = RuleGenerator(db)
    proposed = generator.get_suggested_rules()

    # Filter out already-existing rules
    existing_patterns = set()
    existing_rules = db.query(EmailRule).filter(EmailRule.dismissed == False).all()
    for rule in existing_rules:
        existing_patterns.add((rule.rule_type, rule.pattern, rule.action, rule.folder))

    suggested = []
    for rule in proposed:
        key = (rule.rule_type, rule.pattern, rule.action, rule.folder)
        if key not in existing_patterns:
            # Store as pending rule
            db_rule = EmailRule(
                rule_type=rule.rule_type,
                pattern=rule.pattern,
                action=rule.action,
                folder=rule.folder
            )
            db.add(db_rule)
            db.flush()
            suggested.append(SuggestedRule(
                id=db_rule.id,
                rule_type=rule.rule_type,
                pattern=rule.pattern,
                action=rule.action,
                folder=rule.folder,
                evidence_count=rule.evidence_count
            ))

    db.commit()

    # Get applied rules
    applied_rules = db.query(EmailRule).filter(
        EmailRule.fastmail_rule_id.isnot(None)
    ).all()

    applied = [
        AppliedRule(
            id=r.id,
            rule_type=r.rule_type,
            pattern=r.pattern,
            action=r.action,
            folder=r.folder,
            applied_at=r.applied_at
        )
        for r in applied_rules
    ]

    return RulesResponse(
        suggested=suggested,
        applied=applied,
        provider=provider_name,
        rules_supported=rules_supported
    )


@router.get("/{rule_id}/sieve", response_model=SieveResponse)
async def get_sieve(rule_id: int, db: Session = Depends(get_db)):
    """Get sieve code for a rule."""
    rule = db.query(EmailRule).filter(EmailRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    proposed = ProposedRule(
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        action=rule.action,
        folder=rule.folder,
        evidence_count=0
    )
    sieve = RuleGenerator.generate_sieve(proposed)
    return SieveResponse(sieve=sieve)


@router.post("/{rule_id}/apply", response_model=SuccessResponse)
async def apply_rule(rule_id: int, db: Session = Depends(get_db)):
    """Apply a rule to Fastmail."""
    rule = db.query(EmailRule).filter(EmailRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    provider_name = _get_setting(db, "email_provider") or "gmail"
    if provider_name != "fastmail":
        return SuccessResponse(success=False, error="Rules only supported for Fastmail")

    try:
        provider = get_active_provider()
        proposed = ProposedRule(
            rule_type=rule.rule_type,
            pattern=rule.pattern,
            action=rule.action,
            folder=rule.folder,
            evidence_count=0
        )
        fastmail_id = await provider.create_filter_rule(proposed)

        if fastmail_id:
            rule.fastmail_rule_id = fastmail_id
            rule.applied_at = datetime.now().isoformat()
            db.commit()
            return SuccessResponse(success=True, fastmail_rule_id=fastmail_id)
        else:
            return SuccessResponse(success=False, error="Failed to create rule in Fastmail")
    except Exception as e:
        logging.error(f"Error applying rule: {e}")
        return SuccessResponse(success=False, error=str(e))


@router.post("/{rule_id}/dismiss", response_model=SuccessResponse)
async def dismiss_rule(rule_id: int, db: Session = Depends(get_db)):
    """Dismiss a suggested rule."""
    rule = db.query(EmailRule).filter(EmailRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.dismissed = True
    db.commit()
    return SuccessResponse(success=True)


@router.delete("/{rule_id}", response_model=SuccessResponse)
async def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete a rule (removes from Fastmail if applied)."""
    rule = db.query(EmailRule).filter(EmailRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # If applied to Fastmail, remove it there too
    if rule.fastmail_rule_id:
        try:
            provider = get_active_provider()
            await provider.delete_filter_rule(rule.fastmail_rule_id)
        except Exception as e:
            logging.error(f"Error removing Fastmail rule: {e}")

    db.delete(rule)
    db.commit()
    return SuccessResponse(success=True)
```

**Step 4: Add router to main.py**

In `src/main.py`:

```python
from routes.rules import router as rules_router
# ...
app.include_router(rules_router, prefix="/api")
```

**Step 5: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_rules_api.py -v`

Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add src/routes/rules.py src/main.py tests/test_rules_api.py
git commit -m "feat: add rules API endpoints for sieve generation"
```

---

## Task 9: Fastmail Filter Rule Creation (JMAP)

**Files:**
- Modify: `src/clients/email_provider/fastmail.py`
- Test: `tests/test_fastmail_filters.py`

**Step 1: Write the failing test**

Create `tests/test_fastmail_filters.py`:

```python
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
    """create_filter_rule creates spam filter in Fastmail."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="spammy.com",
        action="spam",
        evidence_count=4
    )

    # Mock the sieve script update
    mock_result = MagicMock()
    mock_result.updated = {"singleton": True}

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
        with patch.object(provider, '_get_account_id', return_value="u123"):
            with patch.object(provider, '_get_existing_sieve', return_value=""):
                rule_id = await provider.create_filter_rule(rule)

    assert rule_id is not None


@pytest.mark.asyncio
async def test_create_filter_rule_categorize(provider):
    """create_filter_rule creates categorize filter."""
    rule = ProposedRule(
        rule_type="domain",
        pattern="substack.com",
        action="categorize",
        folder="Newsletters",
        evidence_count=3
    )

    mock_result = MagicMock()
    mock_result.updated = {"singleton": True}

    with patch.object(provider, '_get_client') as mock_client:
        mock_client.return_value.request.return_value = mock_result
        with patch.object(provider, '_get_account_id', return_value="u123"):
            with patch.object(provider, '_get_existing_sieve', return_value=""):
                rule_id = await provider.create_filter_rule(rule)

    assert rule_id is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_fastmail_filters.py -v`

Expected: FAIL

**Step 3: Add filter methods to fastmail.py**

Add to `FastmailProvider` class in `src/clients/email_provider/fastmail.py`:

```python
    async def _get_existing_sieve(self) -> str:
        """Get existing sieve script from Fastmail."""
        try:
            client = self._get_client()
            account_id = self._get_account_id()

            # Fastmail stores sieve in a special location
            # Using JMAP SieveScript/get
            from jmapc.methods import SieveScriptGet
            sieve_get = SieveScriptGet()
            sieve_get.account_id = account_id
            result = client.request(sieve_get)

            # Find the active script
            for script in result.data:
                if script.is_active:
                    return script.content or ""
            return ""
        except Exception as e:
            logging.warning(f"Could not get existing sieve: {e}")
            return ""

    async def create_filter_rule(self, rule: "ProposedRule") -> Optional[str]:
        """Create a sieve filter rule in Fastmail.

        Fastmail uses JMAP SieveScript for filters. We append our rule
        to the existing script.
        """
        from core.rule_generator import RuleGenerator

        try:
            client = self._get_client()
            account_id = self._get_account_id()

            # Generate sieve code for this rule
            sieve_code = RuleGenerator.generate_sieve(rule)
            if not sieve_code:
                return None

            # Get existing script
            existing = await self._get_existing_sieve()

            # Add comment marker for tracking
            rule_marker = f"# Privemail rule: {rule.rule_type}:{rule.pattern}:{rule.action}"
            new_rule_block = f"\n{rule_marker}\n{sieve_code}\n"

            # Prepend our rules (so they run first)
            new_script = new_rule_block + existing

            # Update the script
            from jmapc.methods import SieveScriptSet
            from jmapc.models import SieveScript

            sieve_set = SieveScriptSet(
                update={
                    "singleton": SieveScript(content=new_script, is_active=True)
                }
            )
            sieve_set.account_id = account_id
            result = client.request(sieve_set)

            if result.updated and "singleton" in result.updated:
                # Return a synthetic ID based on the rule
                return f"privemail:{rule.rule_type}:{rule.pattern}"

            return None
        except Exception as e:
            logging.error(f"Error creating filter rule: {e}")
            return None

    async def delete_filter_rule(self, rule_id: str) -> bool:
        """Delete a filter rule from Fastmail.

        Removes the rule block from the sieve script.
        """
        if not rule_id.startswith("privemail:"):
            return False

        try:
            client = self._get_client()
            account_id = self._get_account_id()

            # Parse rule_id to find the marker
            parts = rule_id.split(":", 2)
            if len(parts) < 3:
                return False

            rule_type, pattern = parts[1], parts[2]
            marker = f"# Privemail rule: {rule_type}:{pattern}"

            # Get existing script
            existing = await self._get_existing_sieve()

            # Remove lines between marker and next rule/end
            lines = existing.split("\n")
            new_lines = []
            skip_until_next = False

            for line in lines:
                if marker in line:
                    skip_until_next = True
                    continue
                if skip_until_next:
                    # Skip the if statement and closing brace
                    if line.strip().startswith("if ") or line.strip() == "}" or not line.strip():
                        continue
                    skip_until_next = False
                new_lines.append(line)

            new_script = "\n".join(new_lines)

            # Update the script
            from jmapc.methods import SieveScriptSet
            from jmapc.models import SieveScript

            sieve_set = SieveScriptSet(
                update={
                    "singleton": SieveScript(content=new_script, is_active=True)
                }
            )
            sieve_set.account_id = account_id
            result = client.request(sieve_set)

            return result.updated and "singleton" in result.updated
        except Exception as e:
            logging.error(f"Error deleting filter rule: {e}")
            return False
```

Add the TYPE_CHECKING import at top:
```python
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.rule_generator import ProposedRule
```

**Step 4: Run test to verify it passes**

Run: `cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/test_fastmail_filters.py -v`

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/clients/email_provider/fastmail.py tests/test_fastmail_filters.py
git commit -m "feat: add Fastmail sieve filter rule creation via JMAP"
```

---

## Task 10: Run Full Test Suite

**Step 1: Run all tests**

```bash
cd /home/offsetkeyz/projects/privemail-email-providers && uv run pytest tests/ -v
```

Expected: All tests PASS

**Step 2: Fix any failures**

If any tests fail, fix them before proceeding.

**Step 3: Commit if fixes were needed**

```bash
git add -A
git commit -m "fix: resolve test failures"
```

---

## Summary

After completing all tasks, you'll have:

1. **Database models** for classifications, rules, and folders
2. **RuleGenerator** ported from fastmail_sorter with SQLAlchemy
3. **Provider methods** for move/folder operations on both Gmail and Fastmail
4. **API endpoints** for:
   - `POST /api/emails/{id}/classify` - classify and move emails
   - `GET/POST /api/folders` - list and create folders
   - `GET /api/rules` - get suggested and applied rules
   - `GET /api/rules/{id}/sieve` - get sieve code
   - `POST /api/rules/{id}/apply` - apply rule to Fastmail
   - `POST /api/rules/{id}/dismiss` - dismiss suggestion
   - `DELETE /api/rules/{id}` - delete rule
5. **Fastmail JMAP integration** for creating sieve filter rules

Frontend work (buttons, modals, Rules page) is not included in this plan - that would be a separate frontend task.

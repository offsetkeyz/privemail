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
        """Fetch unread messages from inbox.

        Args:
            limit: Maximum number of messages to fetch

        Returns:
            List of EmailMessage objects
        """
        pass

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body text
            reply_to_id: Optional message ID this is replying to

        Returns:
            SendResult indicating success/failure
        """
        pass

    @abstractmethod
    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Create a draft in the provider.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body text
            reply_to_id: Optional message ID this is replying to

        Returns:
            SendResult indicating success/failure
        """
        pass

    @abstractmethod
    async def get_contacts(self) -> List[Dict[str, Any]]:
        """Fetch contacts from provider.

        Returns:
            List of contact dicts with 'name' and 'email' keys
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Verify credentials are valid.

        Returns:
            True if connection successful, False otherwise
        """
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

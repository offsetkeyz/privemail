"""Gmail provider implementation wrapping existing google.py."""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import EmailProvider, EmailMessage, SendResult, MoveResult, Mailbox
from .validation import is_valid_email
import clients.google as google_client

logging.basicConfig(level=logging.INFO)


class GmailProvider(EmailProvider):
    """Gmail implementation using existing google.py functions."""

    def __init__(self):
        """Initialize Gmail provider."""
        self._service = None

    @property
    def provider_name(self) -> str:
        return "gmail"

    def _get_service(self):
        """Get or create Gmail service."""
        if self._service is None:
            self._service = google_client.get_gmail_service()
        return self._service

    async def test_connection(self) -> bool:
        """Test Gmail connection."""
        try:
            service = await asyncio.to_thread(self._get_service)
            return service is not None
        except Exception as e:
            logging.error(f"Gmail connection test failed: {e}")
            return False

    async def fetch_unread_messages(self, limit: int = 10) -> List[EmailMessage]:
        """Fetch unread messages from Gmail."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return []

        try:
            stubs = await asyncio.to_thread(google_client.fetch_new_email_stubs, service)
            messages = []

            for message_id in stubs[:limit]:
                details = await asyncio.to_thread(google_client.fetch_email_details, service, message_id)
                if details:
                    messages.append(EmailMessage(
                        message_id=details["message_id"],
                        sender=details["sender"],
                        subject=details["subject"],
                        body_text=details["body_text"],
                        received_at=details.get("received_at")
                    ))

            return messages
        except Exception as e:
            logging.error(f"Error fetching Gmail messages: {e}")
            return []

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Send email via Gmail."""
        # Validate email address
        if not is_valid_email(to):
            return SendResult(success=False, error=f"Invalid email address: {to}")

        service = await asyncio.to_thread(self._get_service)
        if not service:
            return SendResult(success=False, error="Gmail service unavailable")

        try:
            success = await asyncio.to_thread(google_client.send_reply, service, to, subject, body)
            return SendResult(success=success, error=None if success else "Send failed")
        except Exception as e:
            logging.error(f"Error sending Gmail: {e}")
            return SendResult(success=False, error=str(e))

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: Optional[str] = None
    ) -> SendResult:
        """Create draft in Gmail."""
        # Validate email address
        if not is_valid_email(to):
            return SendResult(success=False, error=f"Invalid email address: {to}")

        service = await asyncio.to_thread(self._get_service)
        if not service:
            return SendResult(success=False, error="Gmail service unavailable")

        try:
            success = await asyncio.to_thread(google_client.create_draft, service, to, subject, body)
            return SendResult(success=success, error=None if success else "Draft creation failed")
        except Exception as e:
            logging.error(f"Error creating Gmail draft: {e}")
            return SendResult(success=False, error=str(e))

    async def get_contacts(self) -> List[Dict[str, Any]]:
        """Fetch contacts from Google."""
        service = await asyncio.to_thread(self._get_service)
        if not service:
            return []

        try:
            return await asyncio.to_thread(google_client.fetch_google_contacts, service)
        except Exception as e:
            logging.error(f"Error fetching Google contacts: {e}")
            return []

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

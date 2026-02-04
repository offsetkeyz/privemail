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

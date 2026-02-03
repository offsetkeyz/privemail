import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from models.schemas import InboxItem
from database.db import get_db, Draft, Email, Setting

router = APIRouter(
    prefix="/inbox",
    tags=["Inbox"],
)


def _get_setting(db: Session, key: str) -> str | None:
    """Get a setting from database."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else None


@router.get("/", response_model=List[InboxItem])
def get_inbox_list(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """
    Fetches all processed emails for the active provider.
    Sorted by urgency. Excludes archived and replied emails.
    """
    try:
        # Get active provider
        active_provider = _get_setting(db, "email_provider") or "gmail"

        offset = (page - 1) * page_size
        results = (
            db.query(
                Email.id.label("email_id"),
                Email.sender.label("correspondent"),
                Email.subject,
                Email.local_priority_score,
                Draft.id.label("draft_id")
            )
            .outerjoin(Draft, Email.id == Draft.email_id)
            .filter(Email.status.notin_(["archived_no_reply", "replied"]))
            .filter(Email.provider == active_provider)
            .order_by(desc(Email.local_priority_score))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        
        inbox_items = []
        for email in results:
            inbox_items.append(
                InboxItem(
                    email_id=email.email_id,
                    correspondent=email.correspondent,
                    subject=email.subject,
                    has_draft=(email.draft_id is not None),
                    draft_id=email.draft_id,
                    local_priority_score=email.local_priority_score or 0.0
                )
            )
        return inbox_items
    except Exception as e:
        print(f"Error fetching inbox list: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch inbox list")
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

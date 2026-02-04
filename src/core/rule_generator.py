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

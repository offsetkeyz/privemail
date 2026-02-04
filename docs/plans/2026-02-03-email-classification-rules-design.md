# Email Classification & Rules Design

**Goal:** Allow users to classify emails (spam, wanted, categorize) with quick actions, then generate Fastmail sieve rules from learned patterns.

**Key Decisions:**
- Three classifications: Spam, Wanted, Categorize (no Ignore)
- Quick action buttons on inbox list and email detail view
- Emails move immediately when classified
- Dedicated Rules page in Settings with badge for new suggestions
- Both options for rules: copy sieve code OR apply via Fastmail API
- Classification works on both providers; rules only for Fastmail (Gmail support planned)
- Reuse logic from `offsetkeyz/fastmail_sorter` CLI tool

---

## Classification UI

### Inbox List View

Each email row gets a hover-reveal action bar:
```
┌────────────────────────────────────────────────────────────┐
│ newsletter@company.com                      [🗑️] [📁] [✓] │
│   Weekly digest for January...                             │
└────────────────────────────────────────────────────────────┘
```
- 🗑️ = Mark as Spam (moves to Spam folder)
- 📁 = Categorize (opens folder picker)
- ✓ = Mark as Wanted (keeps in Inbox, records as trusted)

### Email Detail View

Same three buttons in the email header toolbar with labels:
```
[← Back]                          [Spam] [Categorize] [Wanted]
```

### Folder Picker Modal

```
┌─────────────────────────────────┐
│ Move to folder                  │
├─────────────────────────────────┤
│ ○ Newsletters                   │
│ ○ Receipts                      │
│ ○ Archive                       │
├─────────────────────────────────┤
│ + Create new folder...          │
├─────────────────────────────────┤
│         [Cancel] [Move]         │
└─────────────────────────────────┘
```

Folders sorted by recent use. Creating a new folder creates it in the provider via API.

---

## Rules Page

**Location:** Settings > Email Rules (badge shows count of new suggestions)

```
Email Rules                                    [Fastmail ▾]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Suggested Rules (3 new)
───────────────────────────────────────────────────────────
These rules are based on your recent classifications.

┌─────────────────────────────────────────────────────────┐
│ 🗑️ Spam: emails from marketingblast.com                 │
│    Based on: 4 emails marked as spam                    │
│    [Copy Sieve] [Apply to Fastmail]           [Dismiss] │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ 📁 File to Newsletters: emails from substack.com        │
│    Based on: 3 emails categorized to Newsletters        │
│    [Copy Sieve] [Apply to Fastmail]           [Dismiss] │
└─────────────────────────────────────────────────────────┘

Applied Rules
───────────────────────────────────────────────────────────
┌─────────────────────────────────────────────────────────┐
│ 🗑️ Spam: emails from spammer.net                        │
│    Applied: Jan 28, 2026                    [Remove]    │
└─────────────────────────────────────────────────────────┘
```

**Thresholds:**
- Domain-based rules: 3+ emails with same classification
- Sender-based rules: 2+ emails with same classification

**Copy Sieve Modal:**
```
┌─────────────────────────────────────────────────────────┐
│ Sieve Code                                    [Copy]    │
├─────────────────────────────────────────────────────────┤
│ if address :domain "from" "marketingblast.com" {        │
│     fileinto "Spam"; stop;                              │
│ }                                                       │
├─────────────────────────────────────────────────────────┤
│ Paste into Fastmail > Settings > Filters > Edit custom  │
│ sieve code                                              │
└─────────────────────────────────────────────────────────┘
```

**Gmail Behavior:** Shows classifications but displays: "Filter rules available when using Fastmail. Gmail filter support coming soon."

---

## Database Schema

### email_classifications

```sql
CREATE TABLE email_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL REFERENCES emails(id),
    sender TEXT NOT NULL,
    sender_domain TEXT NOT NULL,
    classification TEXT NOT NULL,  -- 'spam', 'wanted', 'categorize'
    folder TEXT,                   -- target folder for 'categorize'
    provider TEXT NOT NULL,        -- 'gmail' or 'fastmail'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_classifications_domain ON email_classifications(sender_domain);
CREATE INDEX ix_classifications_sender ON email_classifications(sender);
```

### email_rules

```sql
CREATE TABLE email_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,       -- 'sender' or 'domain'
    pattern TEXT NOT NULL,
    action TEXT NOT NULL,          -- 'spam', 'wanted', 'categorize'
    folder TEXT,                   -- for 'categorize' rules
    fastmail_rule_id TEXT,         -- NULL if not applied, JMAP ID if applied
    dismissed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP,
    UNIQUE(rule_type, pattern, action, folder)
);
```

### user_folders

```sql
CREATE TABLE user_folders (
    folder_name TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    use_count INTEGER DEFAULT 1,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### Classification

```
POST /api/emails/{id}/classify
Body: {"classification": "spam" | "wanted" | "categorize", "folder": "Newsletters"}
Response: {"success": true, "moved_to": "Spam"}
```

### Folders

```
GET /api/folders
Response: {"folders": [{"name": "Newsletters", "use_count": 5}, ...]}

POST /api/folders
Body: {"name": "Receipts"}
Response: {"success": true, "folder": "Receipts"}
```

### Rules

```
GET /api/rules
Response: {
    "suggested": [...],
    "applied": [...],
    "provider": "fastmail",
    "rules_supported": true
}

POST /api/rules/{id}/apply
Response: {"success": true, "fastmail_rule_id": "Mf1234"}

POST /api/rules/{id}/dismiss
Response: {"success": true}

DELETE /api/rules/{id}
Response: {"success": true}

GET /api/rules/{id}/sieve
Response: {"sieve": "if address :domain \"from\" \"spam.com\" { ... }"}
```

---

## Provider Integration

### New Methods on EmailProvider ABC

```python
async def move_to_folder(self, email_id: str, folder: str) -> bool
async def move_to_spam(self, email_id: str) -> bool
async def get_mailboxes(self) -> list[dict]
async def create_mailbox(self, name: str) -> str
async def create_filter_rule(self, rule: ProposedRule) -> str  # Fastmail only
async def delete_filter_rule(self, rule_id: str) -> bool       # Fastmail only
```

### Code Reuse from fastmail_sorter

| fastmail_sorter | Privemail Location |
|-----------------|-------------------|
| `rules.py` | `src/core/rule_generator.py` |
| `ProposedRule` dataclass | Reuse directly |
| `generate_sieve()` | Reuse directly |
| Threshold queries | Adapt to SQLAlchemy |

---

## Implementation Order

| Phase | Tasks | Risk |
|-------|-------|------|
| 1 | Database migration (3 new tables) | Low |
| 2 | Port RuleGenerator from fastmail_sorter | Low |
| 3 | Add provider methods (move, mailboxes, filters) | Medium |
| 4 | API endpoints (classify, folders, rules) | Low |
| 5 | Frontend (buttons, folder picker, Rules page) | Low |

---

## Testing

**Unit Tests:**
- RuleGenerator threshold logic
- Sieve code generation

**Integration Tests:**
- Provider move_to_folder, create_filter_rule (mocked JMAP)
- Classification API flow

**Manual E2E:**
- [ ] Mark email as spam → moves to Spam folder
- [ ] Categorize email → folder picker works, email moves
- [ ] Create new folder → appears in Fastmail
- [ ] Mark 3+ from same domain as spam → rule suggested
- [ ] Apply rule → filter created in Fastmail
- [ ] Copy sieve → correct code displayed
- [ ] Switch to Gmail → classification works, rules disabled

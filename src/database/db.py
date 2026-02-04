import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, ForeignKey, Float
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
from sqlalchemy.exc import OperationalError

# FIX: Import get_data_dir
from core.path_utils import get_data_dir

try:
    from core.encryption import EncryptedText
except ImportError:
    logging.warning("core.encryption.EncryptedText not found. Using simple Text.")
    EncryptedText = Text

# FIX: Define DB path in the writable User Data directory
DB_PATH = get_data_dir() / "app.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure the directory exists before connecting (Safety check)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# ... (Rest of your models: Email, Draft, Group, Contact, Setting remain unchanged) ...
# Copy the rest of your existing db.py file here starting from class Email(Base):
# or I can provide the full file if you prefer.

class Email(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True)
    sender = Column(String, index=True)
    subject = Column(EncryptedText)
    body_text = Column(EncryptedText)
    status = Column(String)
    correspondent_tone = Column(Text, nullable=True)
    correspondent_goal = Column(Text, nullable=True)
    correspondent_evidence = Column(Text, nullable=True)
    local_priority_score = Column(Float, default=0.0, index=True)
    provider = Column(String, default="gmail", index=True)
    drafts = relationship("Draft", back_populates="email")

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    generated_text = Column(EncryptedText)
    final_text = Column(EncryptedText)
    status = Column(String)
    is_read_and_confirmed = Column(Boolean, default=False, nullable=False)
    provider = Column(String, default="gmail")
    email = relationship("Email", back_populates="drafts")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    group_goal = Column(Text, nullable=True)
    group_tone = Column(Text, nullable=True)
    group_urgency = Column(Float, nullable=True)
    color = Column(String, default="#ffffff") 
    contacts = relationship("Contact", back_populates="group")

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    email_address = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group = relationship("Group", back_populates="contacts")
    contact_group = Column(Text, nullable=True)
    tone = Column(Text, nullable=True)
    tone_strength = Column(Float, nullable=True)
    goal = Column(Text, nullable=True)
    auto_draft_enabled = Column(Boolean, default=True, nullable=False)
    style_sample_text = Column(EncryptedText, nullable=True)
    source_providers = Column(Text, default='["google"]')

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String)


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


def migrate_schema_if_needed():
    """Add provider columns if they don't exist."""
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(engine)

        # Migrate Email table
        email_columns = [c['name'] for c in inspector.get_columns('emails')]
        if 'provider' not in email_columns:
            logging.info("Migrating Email table: adding provider column...")
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE emails ADD COLUMN provider VARCHAR DEFAULT "gmail"'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_emails_provider ON emails(provider)'))
                conn.commit()
            logging.info("Email table migration completed.")

        # Migrate Draft table
        draft_columns = [c['name'] for c in inspector.get_columns('drafts')]
        if 'provider' not in draft_columns:
            logging.info("Migrating Draft table: adding provider column...")
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE drafts ADD COLUMN provider VARCHAR DEFAULT "gmail"'))
                conn.commit()
            logging.info("Draft table migration completed.")

        # Migrate Contact table
        contact_columns = [c['name'] for c in inspector.get_columns('contacts')]
        if 'source_providers' not in contact_columns:
            logging.info("Migrating Contact table: adding source_providers column...")
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE contacts ADD COLUMN source_providers TEXT DEFAULT \'["google"]\''))
                conn.commit()
            logging.info("Contact table migration completed.")

    except Exception as e:
        logging.error(f"Schema migration failed: {e}")
        # Don't raise - let application continue with new installs


def create_db_and_tables():
    try:
        logging.info(f"Attempting to create database tables at {DB_PATH}...")
        Base.metadata.create_all(bind=engine)
        logging.info("Database tables verified/created successfully.")

        # Run migrations for existing databases
        migrate_schema_if_needed()

    except OperationalError as e:
        logging.error(f"FATAL: Database operation failed: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during table creation: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
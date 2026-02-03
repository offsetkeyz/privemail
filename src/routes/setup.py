import os
import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

# Import core components
from database import db, db_manager
from clients import google as google_client
from clients import ai_engine as ollama_client
from clients.email_provider import FastmailProvider
from core.config import SETUP_COMPLETE_FLAG_PATH, DEFAULT_OLLAMA_MODEL
from scheduler import _set_setting
# FIX: Import get_data_dir
from core.path_utils import get_data_dir

router = APIRouter(prefix="/setup", tags=["Setup"])

# FIX: Use writable User Data directory
DATA_DIR = get_data_dir()
SECRETS_FILE = DATA_DIR / "secrets.json"


class SetupInitRequest(BaseModel):
    master_password: str
    model_name: str


@router.get("/status")
async def get_setup_status():
    # FIX: Check token in DATA_DIR
    token_path = DATA_DIR / "token.json"

    # Check setup flag in DATA_DIR
    setup_flag = DATA_DIR / ".setup_complete"

    google_token_exists = token_path.exists()
    ollama_running = await ollama_client.check_ollama_status()

    # Check Fastmail configuration
    session = db.SessionLocal()
    try:
        fastmail_key = session.query(db.Setting).filter(
            db.Setting.key == "fastmail_api_key").first()
        fastmail_configured = fastmail_key is not None and fastmail_key.value is not None

        active_provider_setting = session.query(db.Setting).filter(
            db.Setting.key == "email_provider").first()
        active_provider = active_provider_setting.value if active_provider_setting else "gmail"
    finally:
        session.close()

    return {
        "google_connected": google_token_exists,
        "fastmail_connected": fastmail_configured,
        "active_provider": active_provider,
        "ollama_running": ollama_running,
        "setup_complete": setup_flag.exists()
    }


@router.get("/auth")
def trigger_auth_flow():
    """Forces the Google Auth flow to start on the server."""
    service = google_client.get_gmail_service()
    if service:
        return {"status": "already_connected"}
    else:
        return {"status": "flow_started"}


@router.post("/complete")
def complete_setup(request: SetupInitRequest):
    try:
        logging.info("SETUP: Initializing application...")

        # 1. Ensure data dir exists (Should be handled by get_data_dir, but safe to check)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Save Master Password
        with open(SECRETS_FILE, "w") as f:
            json.dump({"master_password": request.master_password}, f)

        # 3. Initialize Database & Encryption
        # (db.py now uses get_data_dir internally, so this is safe)
        db.create_db_and_tables()
        db_manager.initialize_encryption(request.master_password)

        # 4. Save Settings to DB
        session = db.SessionLocal()
        try:
            _set_setting(session, "ollama_model", request.model_name)
            _set_setting(session, "scan_interval", "300")
        finally:
            session.close()

        # 5. Mark Setup as Complete in DATA_DIR
        (DATA_DIR / ".setup_complete").touch()

        logging.info("SETUP: Setup process finished successfully.")
        return {"status": "success"}

    except Exception as e:
        logging.error(f"SETUP ERROR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class FastmailSetupRequest(BaseModel):
    api_key: str


@router.post("/fastmail")
async def setup_fastmail(request: FastmailSetupRequest):
    """Setup Fastmail with API key."""
    try:
        # Ensure database exists before saving settings
        db.create_db_and_tables()

        # Test connection
        provider = FastmailProvider(api_token=request.api_key)

        if not await provider.test_connection():
            return {"success": False, "error": "Connection failed. Check your API key."}

        # Get account info
        account_id = provider._get_account_id()
        sender_email = provider._get_sender_email()

        # Save credentials to database
        session = db.SessionLocal()
        try:
            _set_setting(session, "fastmail_api_key", request.api_key)
            _set_setting(session, "fastmail_account_id", account_id)
            # Don't switch provider automatically - let user choose
        finally:
            session.close()

        logging.info(f"SETUP: Fastmail connected for {sender_email}")
        return {
            "success": True,
            "account_id": account_id,
            "email": sender_email
        }

    except Exception as e:
        logging.error(f"Fastmail setup failed: {e}")
        return {"success": False, "error": str(e)}

import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from typing import List, Dict
from sqlalchemy.orm import Session

from models.schemas import (
    GenerationRequest,
    ModelItem,
    SettingsUpdateRequest,
    ModelSettingRequest
)
import clients.ai_engine as ollama_client
from clients.email_provider import get_provider_by_name
from database.db import get_db, Setting
from scheduler import _get_setting, _set_setting
from core.path_utils import get_data_dir

router = APIRouter(
    tags=["System & Models"],
)

# --- System Status ---


@router.get("/status")
async def get_status():
    is_running = await ollama_client.check_ollama_status()
    if is_running:
        return {"status": "Ollama server is running"}
    else:
        raise HTTPException(status_code=503, detail="Ollama server is offline")


@router.post("/system/unload")
async def unload_ai_model():
    """Forcefully unloads the AI model to free resources."""
    await ollama_client.unload_model()
    return {"status": "success", "message": "AI Model Unload Signal Sent"}

# --- Settings Endpoints ---


@router.get("/settings", response_model=Dict[str, str])
async def get_all_settings(db: Session = Depends(get_db)):
    settings = db.query(Setting).all()
    return {s.key: s.value for s in settings}


@router.post("/settings")
async def update_settings(
    request: SettingsUpdateRequest,
    db: Session = Depends(get_db)
):
    try:
        for item in request.settings:
            _set_setting(db, item.key, item.value)
        db.commit()
        return {"status": "success", "message": "Settings updated."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update settings: {e}")


@router.post("/settings/model")
async def set_default_model(
    request: ModelSettingRequest,
    db: Session = Depends(get_db)
):
    try:
        _set_setting(db, "ollama_model", request.model_name)
        return {"status": "success", "message": f"Default model set to {request.model_name}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to set model: {e}")


@router.post("/settings/pause")
async def toggle_pause(enabled: bool, db: Session = Depends(get_db)):
    """Pauses or Resumes the background scheduler."""
    # 'enabled' here means "is pause enabled?" (True = Paused)
    _set_setting(db, "scheduler_paused", str(enabled).lower())
    return {"status": "success", "paused": enabled}

# --- Model & AI Endpoints ---


@router.get("/models", response_model=List[str])
async def get_installed_models_list():
    try:
        models = await ollama_client.list_installed_models()
        return models
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/list/{selected_model}", response_model=List[ModelItem])
async def get_models(selected_model: str):
    if selected_model.lower() in ["null", "undefined", "none"]:
        selected_model = ""
    models = await ollama_client.list_local_models(selected_model)
    return models


@router.post("/generate", response_class=PlainTextResponse)
async def post_generate(request: GenerationRequest):
    try:
        output = await ollama_client.generate_text(request)
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Provider Management Endpoints ---


@router.get("/providers")
async def get_providers(db: Session = Depends(get_db)):
    """Get configured email providers."""
    # Check Gmail
    token_path = get_data_dir() / "token.json"
    gmail_configured = token_path.exists()

    # Check Fastmail
    fastmail_key = db.query(Setting).filter(Setting.key == "fastmail_api_key").first()
    fastmail_configured = fastmail_key is not None and fastmail_key.value is not None

    # Get active
    active_setting = db.query(Setting).filter(Setting.key == "email_provider").first()
    active = active_setting.value if active_setting else "gmail"

    configured = []
    if gmail_configured:
        configured.append("gmail")
    if fastmail_configured:
        configured.append("fastmail")

    return {
        "active": active,
        "configured": configured,
        "available": ["gmail", "fastmail"]
    }


@router.post("/provider")
async def switch_provider(request: dict, db: Session = Depends(get_db)):
    """Switch active email provider."""
    provider_name = request.get("provider")

    if provider_name not in ["gmail", "fastmail"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    # Verify provider is configured
    try:
        provider = get_provider_by_name(provider_name)
        if not await provider.test_connection():
            raise HTTPException(
                status_code=400,
                detail=f"{provider_name} is not properly configured"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update setting
    setting = db.query(Setting).filter(Setting.key == "email_provider").first()
    if setting:
        setting.value = provider_name
    else:
        db.add(Setting(key="email_provider", value=provider_name))
    db.commit()

    return {"success": True, "provider": provider_name}

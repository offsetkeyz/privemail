"""Folder management API routes."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.db import get_db, UserFolder
from clients.email_provider import get_active_provider

router = APIRouter(
    prefix="/folders",
    tags=["Folders"],
)


class FolderInfo(BaseModel):
    name: str
    use_count: int = 0
    from_provider: bool = False


class FoldersResponse(BaseModel):
    folders: List[FolderInfo]


class CreateFolderRequest(BaseModel):
    name: str


class CreateFolderResponse(BaseModel):
    success: bool
    folder: Optional[str] = None
    error: Optional[str] = None


@router.get("/", response_model=FoldersResponse)
async def get_folders(db: Session = Depends(get_db)):
    """Get list of folders, merged from provider and local cache."""
    provider = get_active_provider()

    # Get folders from provider
    provider_mailboxes = await provider.get_mailboxes()
    provider_names = {mb.name for mb in provider_mailboxes}

    # Get cached folder usage
    cached = db.query(UserFolder).order_by(desc(UserFolder.use_count)).all()

    # Merge: start with cached (sorted by use), add provider-only
    folders = []
    seen = set()

    # Add cached folders first (sorted by usage)
    for folder in cached:
        folders.append(FolderInfo(
            name=folder.folder_name,
            use_count=folder.use_count,
            from_provider=folder.folder_name in provider_names
        ))
        seen.add(folder.folder_name)

    # Add provider folders not in cache
    for mb in provider_mailboxes:
        if mb.name not in seen and mb.role not in ('inbox', 'spam', 'drafts', 'sent', 'trash'):
            folders.append(FolderInfo(
                name=mb.name,
                use_count=0,
                from_provider=True
            ))

    return FoldersResponse(folders=folders)


@router.post("/", response_model=CreateFolderResponse)
async def create_folder(
    request: CreateFolderRequest,
    db: Session = Depends(get_db)
):
    """Create a new folder in the email provider."""
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Folder name required")

    provider = get_active_provider()

    try:
        mailbox_id = await provider.create_mailbox(request.name)
        if mailbox_id:
            # Cache the folder
            db.add(UserFolder(
                folder_name=request.name,
                provider=provider.provider_name,
                use_count=1
            ))
            db.commit()
            return CreateFolderResponse(success=True, folder=request.name)
        else:
            return CreateFolderResponse(success=False, error="Failed to create folder")
    except Exception as e:
        logging.error(f"Error creating folder: {e}")
        return CreateFolderResponse(success=False, error=str(e))

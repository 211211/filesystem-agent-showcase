"""
Document management API routes.
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel, Field

from app.config import get_settings, Settings
from app.agent.tools.file_tools import (
    read_file,
    write_file,
    list_directory,
    get_file_info,
    FileSizeExceededError,
    format_file_size,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentInfo(BaseModel):
    """Information about a document."""
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    modified: Optional[float] = None
    extension: Optional[str] = None


class DocumentContent(BaseModel):
    """Document content response."""
    path: str
    content: str
    info: DocumentInfo


class DocumentListResponse(BaseModel):
    """Response for document listing."""
    path: str
    items: list[DocumentInfo]
    total: int


class CreateDocumentRequest(BaseModel):
    """Request to create a new document."""
    path: str = Field(..., description="Path relative to data root")
    content: str = Field(..., description="Document content")


def get_data_root(settings: Settings = Depends(get_settings)) -> Path:
    """Dependency to get the data root path."""
    return settings.data_root


def get_max_file_size(settings: Settings = Depends(get_settings)) -> int:
    """Dependency to get the maximum file size."""
    return settings.max_file_size


def validate_path(path: str, data_root: Path) -> Path:
    """
    Validate and resolve a path within the data root.

    Raises HTTPException if path is invalid or outside data root.
    """
    # Normalize the path
    if path.startswith("/"):
        path = path[1:]

    full_path = (data_root / path).resolve()

    # Security check: ensure path is within data root
    try:
        full_path.relative_to(data_root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Path traversal not allowed"
        )

    return full_path


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    path: str = Query(".", description="Directory path to list (relative to data root)"),
    recursive: bool = Query(False, description="List recursively"),
    data_root: Path = Depends(get_data_root),
):
    """
    List documents in a directory.

    Returns a list of files and subdirectories with their metadata.
    """
    full_path = validate_path(path, data_root)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Directory not found")

    if not full_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    try:
        items = await list_directory(full_path, recursive=recursive)
        return DocumentListResponse(
            path=path,
            items=[DocumentInfo(**item) for item in items],
            total=len(items),
        )
    except Exception as e:
        logger.exception(f"Error listing directory {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{path:path}", response_model=DocumentContent)
async def get_document(
    path: str,
    data_root: Path = Depends(get_data_root),
    max_file_size: int = Depends(get_max_file_size),
):
    """
    Read a document's content.

    Returns the full content of the specified file.
    File size is limited by MAX_FILE_SIZE configuration (default: 10MB).
    """
    full_path = validate_path(path, data_root)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    if full_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    try:
        content = await read_file(full_path, max_size=max_file_size)
        info = await get_file_info(full_path)

        return DocumentContent(
            path=path,
            content=content,
            info=DocumentInfo(**info) if info else DocumentInfo(
                name=full_path.name,
                path=path,
                is_directory=False,
            ),
        )
    except FileSizeExceededError as e:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {format_file_size(e.file_size)}. "
                   f"Maximum allowed: {format_file_size(e.max_size)}"
        )
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Cannot read binary file as text"
        )
    except Exception as e:
        logger.exception(f"Error reading document {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_document(
    request: CreateDocumentRequest,
    data_root: Path = Depends(get_data_root),
    max_file_size: int = Depends(get_max_file_size),
):
    """
    Create a new document.

    Creates a new file with the specified content at the given path.
    Parent directories are created automatically if they don't exist.
    Content size is limited by MAX_FILE_SIZE configuration (default: 10MB).
    """
    full_path = validate_path(request.path, data_root)

    if full_path.exists():
        raise HTTPException(
            status_code=409,
            detail="Document already exists. Use PUT to update."
        )

    try:
        await write_file(full_path, request.content, max_size=max_file_size)
        info = await get_file_info(full_path)

        return {
            "message": "Document created successfully",
            "path": request.path,
            "info": info,
        }
    except FileSizeExceededError as e:
        raise HTTPException(
            status_code=413,
            detail=f"Content too large: {format_file_size(e.file_size)}. "
                   f"Maximum allowed: {format_file_size(e.max_size)}"
        )
    except Exception as e:
        logger.exception(f"Error creating document {request.path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{path:path}")
async def update_document(
    path: str,
    content: str,
    data_root: Path = Depends(get_data_root),
    max_file_size: int = Depends(get_max_file_size),
):
    """
    Update an existing document.

    Replaces the content of an existing file.
    Content size is limited by MAX_FILE_SIZE configuration (default: 10MB).
    """
    full_path = validate_path(path, data_root)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    if full_path.is_dir():
        raise HTTPException(status_code=400, detail="Cannot update a directory")

    try:
        await write_file(full_path, content, max_size=max_file_size)
        info = await get_file_info(full_path)

        return {
            "message": "Document updated successfully",
            "path": path,
            "info": info,
        }
    except FileSizeExceededError as e:
        raise HTTPException(
            status_code=413,
            detail=f"Content too large: {format_file_size(e.file_size)}. "
                   f"Maximum allowed: {format_file_size(e.max_size)}"
        )
    except Exception as e:
        logger.exception(f"Error updating document {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{path:path}")
async def delete_document(
    path: str,
    data_root: Path = Depends(get_data_root),
):
    """
    Delete a document.

    Permanently removes the specified file.
    """
    full_path = validate_path(path, data_root)

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    if full_path.is_dir():
        raise HTTPException(status_code=400, detail="Cannot delete a directory with this endpoint")

    try:
        full_path.unlink()
        return {"message": "Document deleted successfully", "path": path}
    except Exception as e:
        logger.exception(f"Error deleting document {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    path: str = Query(..., description="Target path relative to data root"),
    data_root: Path = Depends(get_data_root),
    max_file_size: int = Depends(get_max_file_size),
):
    """
    Upload a document file.

    Uploads a file to the specified path in the data directory.
    File size is limited by MAX_FILE_SIZE configuration (default: 10MB).
    """
    full_path = validate_path(path, data_root)

    if full_path.exists():
        raise HTTPException(
            status_code=409,
            detail="File already exists at this path"
        )

    try:
        content = await file.read()

        # Check file size
        if len(content) > max_file_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {format_file_size(len(content))}. "
                       f"Maximum allowed: {format_file_size(max_file_size)}"
            )

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)

        info = await get_file_info(full_path)

        return {
            "message": "File uploaded successfully",
            "path": path,
            "filename": file.filename,
            "size": len(content),
            "info": info,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error uploading file to {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

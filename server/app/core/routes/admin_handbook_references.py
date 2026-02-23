import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..dependencies import require_admin

router = APIRouter(prefix="/admin/handbook-references", tags=["admin-handbooks"])

# Base path for handbook references relative to the server/app directory
# docs is at ../../../../docs from server/app/core/routes
BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../docs/references/handbooks"))

class HandbookReference(BaseModel):
    name: str
    type: str  # 'file' or 'directory'
    path: str
    extension: Optional[str] = None

@router.get("", response_model=List[HandbookReference], dependencies=[Depends(require_admin)])
async def list_handbook_references(path: str = ""):
    """List available handbook reference files and directories."""
    target_dir = os.path.abspath(os.path.join(BASE_PATH, path))
    
    # Security check to prevent path traversal
    if not target_dir.startswith(BASE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="Directory not found")
    
    items = []
    try:
        for entry in os.scandir(target_dir):
            # Skip hidden files
            if entry.name.startswith("."):
                continue
                
            items.append(HandbookReference(
                name=entry.name,
                type="directory" if entry.is_dir() else "file",
                path=os.path.relpath(entry.path, BASE_PATH),
                extension=os.path.splitext(entry.name)[1] if entry.is_file() else None
            ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return sorted(items, key=lambda x: (x.type == "file", x.name))

@router.get("/file", dependencies=[Depends(require_admin)])
async def get_handbook_reference_file(path: str):
    """Get the content of a specific handbook reference file."""
    file_path = os.path.abspath(os.path.join(BASE_PATH, path))
    
    # Security check to prevent path traversal
    if not file_path.startswith(BASE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(file_path)

@router.get("/content", dependencies=[Depends(require_admin)])
async def get_handbook_reference_content(path: str):
    """Get the text content of a markdown or text reference file."""
    file_path = os.path.abspath(os.path.join(BASE_PATH, path))
    
    # Security check
    if not file_path.startswith(BASE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Only allow reading text-based files
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in [".md", ".txt", ".json", ".yml", ".yaml", ".js", ".ts", ".html"]:
        raise HTTPException(status_code=400, detail="Only text-based files can be read as content")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "name": os.path.basename(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

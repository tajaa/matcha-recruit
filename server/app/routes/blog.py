import json
from datetime import datetime
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel

from ..database import get_connection
from ..dependencies import get_current_user, require_admin, get_optional_user
from ..models.auth import CurrentUser
from ..models.blog import (
    BlogPost, BlogPostCreate, BlogPostUpdate, BlogPostResponse, BlogListResponse, BlogStatus
)
from ..services.storage import get_storage

router = APIRouter()

@router.get("", response_model=BlogListResponse)
async def list_blogs(
    page: int = 1,
    limit: int = 10,
    status: Optional[BlogStatus] = None,
    tag: Optional[str] = None,
    current_user: Optional[CurrentUser] = Depends(get_optional_user)
):
    """List blog posts. Admins can see all, public only published."""
    
    # Defaults
    if page < 1: page = 1
    if limit < 1: limit = 10
    offset = (page - 1) * limit
    
    async with get_connection() as conn:
        conditions = []
        params = []
        param_idx = 1
        
        # Filter by status
        if status:
            # If requesting non-published, ensure admin
            if status != BlogStatus.PUBLISHED:
                if not current_user or current_user.role != "admin":
                    raise HTTPException(status_code=403, detail="Only admins can view non-published posts")
            conditions.append(f"b.status = ${param_idx}")
            params.append(status.value)
            param_idx += 1
        else:
            # Default behavior: if admin, show all (or filterable), if public, show published only
            if not current_user or current_user.role != "admin":
                 conditions.append(f"b.status = ${param_idx}")
                 params.append(BlogStatus.PUBLISHED.value)
                 param_idx += 1
        
        # Filter by tag
        if tag:
            conditions.append(f"b.tags @> ${param_idx}::jsonb")
            params.append(json.dumps([tag]))
            param_idx += 1
            
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
            
        # Count query
        count_query = f"SELECT COUNT(*) FROM blog_posts b {where_clause}"
        total = await conn.fetchval(count_query, *params)
        
        # Data query
        query = f"""
            SELECT b.*, 
                   COALESCE(u.email, 'Unknown') as author_email,
                   COALESCE(a.name, 'Admin') as author_name
            FROM blog_posts b
            LEFT JOIN users u ON b.author_id = u.id
            LEFT JOIN admins a ON u.id = a.user_id
            {where_clause}
            ORDER BY b.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        rows = await conn.fetch(query, *params, limit, offset)
        
        items = []
        for row in rows:
            data = dict(row)
            # Parse JSONB fields
            if isinstance(data.get("tags"), str):
                data["tags"] = json.loads(data["tags"])
            
            items.append(BlogPostResponse(**data))
            
        return BlogListResponse(items=items, total=total)

@router.get("/{slug}", response_model=BlogPostResponse)
async def get_blog_post(slug: str, current_user: Optional[CurrentUser] = Depends(get_optional_user)):
    """Get a single blog post by slug."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT b.*, 
                   COALESCE(u.email, 'Unknown') as author_email,
                   COALESCE(a.name, 'Admin') as author_name
            FROM blog_posts b
            LEFT JOIN users u ON b.author_id = u.id
            LEFT JOIN admins a ON u.id = a.user_id
            WHERE b.slug = $1
            """,
            slug
        )
        
        if not row:
            raise HTTPException(status_code=404, detail="Blog post not found")
            
        # Check permission if not published
        if row["status"] != BlogStatus.PUBLISHED.value:
            if not current_user or current_user.role != "admin":
                 raise HTTPException(status_code=404, detail="Blog post not found")
        
        data = dict(row)
        if isinstance(data.get("tags"), str):
            data["tags"] = json.loads(data["tags"])
            
        return BlogPostResponse(**data)

@router.post("", response_model=BlogPostResponse)
async def create_blog_post(
    post: BlogPostCreate,
    current_user: CurrentUser = Depends(require_admin)
):
    """Create a new blog post."""
    async with get_connection() as conn:
        # Check slug uniqueness
        exists = await conn.fetchval("SELECT 1 FROM blog_posts WHERE slug = $1", post.slug)
        if exists:
            raise HTTPException(status_code=400, detail="Slug already exists")
            
        # Set published_at if status is published
        published_at = None
        if post.status == BlogStatus.PUBLISHED:
            published_at = datetime.utcnow()
            
        row = await conn.fetchrow(
            """
            INSERT INTO blog_posts (
                author_id, title, slug, content, excerpt, cover_image, 
                status, tags, meta_title, meta_description, published_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, created_at, updated_at, published_at, author_id
            """,
            current_user.id,
            post.title,
            post.slug,
            post.content,
            post.excerpt,
            post.cover_image,
            post.status.value,
            json.dumps(post.tags),
            post.meta_title,
            post.meta_description,
            published_at
        )
        
        # Get full object for response
        return await get_blog_post(post.slug, current_user)

@router.put("/{id}", response_model=BlogPostResponse)
async def update_blog_post(
    id: UUID,
    post: BlogPostUpdate,
    current_user: CurrentUser = Depends(require_admin)
):
    """Update a blog post."""
    async with get_connection() as conn:
        # Check existence
        existing = await conn.fetchrow("SELECT id, slug, status FROM blog_posts WHERE id = $1", id)
        if not existing:
             raise HTTPException(status_code=404, detail="Blog post not found")
             
        # Build update query
        fields = []
        params = []
        param_idx = 1
        
        if post.title is not None:
            fields.append(f"title = ${param_idx}")
            params.append(post.title)
            param_idx += 1
            
        if post.slug is not None:
            # Check uniqueness if changed
            if post.slug != existing["slug"]:
                slug_exists = await conn.fetchval("SELECT 1 FROM blog_posts WHERE slug = $1 AND id != $2", post.slug, id)
                if slug_exists:
                    raise HTTPException(status_code=400, detail="Slug already exists")
            fields.append(f"slug = ${param_idx}")
            params.append(post.slug)
            param_idx += 1
            
        if post.content is not None:
            fields.append(f"content = ${param_idx}")
            params.append(post.content)
            param_idx += 1
            
        if post.excerpt is not None:
            fields.append(f"excerpt = ${param_idx}")
            params.append(post.excerpt)
            param_idx += 1
            
        if post.cover_image is not None:
            fields.append(f"cover_image = ${param_idx}")
            params.append(post.cover_image)
            param_idx += 1
            
        if post.status is not None:
            fields.append(f"status = ${param_idx}")
            params.append(post.status.value)
            param_idx += 1
            
            # Update published_at if publishing for the first time or if requested
            if post.status == BlogStatus.PUBLISHED and existing["status"] != "published":
                 fields.append(f"published_at = COALESCE(published_at, NOW())")
        
        if post.tags is not None:
            fields.append(f"tags = ${param_idx}")
            params.append(json.dumps(post.tags))
            param_idx += 1
            
        if post.meta_title is not None:
            fields.append(f"meta_title = ${param_idx}")
            params.append(post.meta_title)
            param_idx += 1
            
        if post.meta_description is not None:
            fields.append(f"meta_description = ${param_idx}")
            params.append(post.meta_description)
            param_idx += 1
            
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
            
        fields.append("updated_at = NOW()")
        params.append(id)
        
        query = f"""
            UPDATE blog_posts
            SET {", ".join(fields)}
            WHERE id = ${param_idx}
            RETURNING slug
        """
        
        new_slug = await conn.fetchval(query, *params)
        
        return await get_blog_post(new_slug, current_user)

@router.delete("/{id}")
async def delete_blog_post(id: UUID, current_user: CurrentUser = Depends(require_admin)):
    """Delete a blog post."""
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM blog_posts WHERE id = $1", id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Blog post not found")
            
    return {"status": "success"}

@router.post("/upload", response_model=dict)
async def upload_blog_image(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin)
):
    """Upload an image for a blog post."""
    storage = get_storage()
    
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")
        
    file_bytes = await file.read()
    
    try:
        url = await storage.upload_file(
            file_bytes,
            file.filename,
            prefix="blog",
            content_type=file.content_type
        )
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

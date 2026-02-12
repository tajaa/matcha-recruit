import json
from datetime import datetime
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user, require_admin, get_optional_user
from ..models.auth import CurrentUser
from ..models.blog import (
    BlogPost, BlogPostCreate, BlogPostUpdate, BlogPostResponse, BlogListResponse, BlogStatus,
    BlogComment, BlogCommentCreate, CommentStatus
)
from ..services.storage import get_storage

router = APIRouter()

# -----------------------------------------------------------------------------
# BLOG POSTS — static routes first, then {slug} catch-all
# -----------------------------------------------------------------------------

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
        return await get_blog_post(post.slug, None, current_user)

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
        print(f"[Blog Upload Error] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# COMMENT ADMIN — must be before /{slug} to avoid route conflict
# -----------------------------------------------------------------------------

@router.get("/comments/pending", response_model=List[BlogComment])
async def list_pending_comments(current_user: CurrentUser = Depends(require_admin)):
    """Admin: List all pending comments."""
    async with get_connection() as conn:
        query = """
            SELECT c.*,
                   COALESCE(u.email, c.author_name, 'Anonymous') as author_name,
                   p.title as post_title
            FROM blog_comments c
            JOIN blog_posts p ON c.post_id = p.id
            LEFT JOIN users u ON c.user_id = u.id
            WHERE c.status = 'pending'
            ORDER BY c.created_at ASC
        """
        rows = await conn.fetch(query)
        return [BlogComment(**row) for row in rows]

@router.patch("/comments/{id}", response_model=BlogComment)
async def moderate_comment(
    id: UUID,
    status: CommentStatus,
    current_user: CurrentUser = Depends(require_admin)
):
    """Admin: Approve or reject a comment."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE blog_comments
            SET status = $1, updated_at = NOW()
            WHERE id = $2
            RETURNING *
            """,
            status.value, id
        )

        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")

        return BlogComment(**row)

# -----------------------------------------------------------------------------
# SLUG-BASED ROUTES — catch-all {slug} must come after static routes
# -----------------------------------------------------------------------------

@router.get("/{slug}", response_model=BlogPostResponse)
async def get_blog_post(
    slug: str,
    session_id: Optional[str] = Query(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user)
):
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

        # Check if liked
        liked = False
        if current_user:
            liked = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM blog_likes WHERE post_id = $1 AND user_id = $2)",
                row["id"], current_user.id
            )
        elif session_id:
            liked = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM blog_likes WHERE post_id = $1 AND session_id = $2)",
                row["id"], session_id
            )

        return BlogPostResponse(**data, liked_by_me=liked)

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

        return await get_blog_post(new_slug, None, current_user)

@router.delete("/{id}")
async def delete_blog_post(id: UUID, current_user: CurrentUser = Depends(require_admin)):
    """Delete a blog post."""
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM blog_posts WHERE id = $1", id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Blog post not found")

    return {"status": "success"}

# -----------------------------------------------------------------------------
# LIKES
# -----------------------------------------------------------------------------

class BlogLikeRequest(BaseModel):
    session_id: Optional[str] = None

class BlogLikeResponse(BaseModel):
    likes_count: int
    liked: bool

@router.post("/{slug}/like", response_model=BlogLikeResponse)
async def toggle_like(
    slug: str,
    request: BlogLikeRequest,
    current_user: Optional[CurrentUser] = Depends(get_optional_user)
):
    """Toggle like on a blog post."""
    async with get_connection() as conn:
        post = await conn.fetchrow("SELECT id, likes_count FROM blog_posts WHERE slug = $1", slug)
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")

        post_id = post["id"]
        user_id = current_user.id if current_user else None
        session_id = request.session_id

        if not user_id and not session_id:
             raise HTTPException(status_code=400, detail="User ID or Session ID required")

        # Check existing like
        if user_id:
            existing = await conn.fetchrow(
                "SELECT id FROM blog_likes WHERE post_id = $1 AND user_id = $2",
                post_id, user_id
            )
        else:
            existing = await conn.fetchrow(
                "SELECT id FROM blog_likes WHERE post_id = $1 AND session_id = $2",
                post_id, session_id
            )

        if existing:
            # Unlike
            await conn.execute("DELETE FROM blog_likes WHERE id = $1", existing["id"])
            new_count = max(0, post["likes_count"] - 1)
            await conn.execute("UPDATE blog_posts SET likes_count = $1 WHERE id = $2", new_count, post_id)
            return BlogLikeResponse(likes_count=new_count, liked=False)
        else:
            # Like
            if user_id:
                 await conn.execute(
                    "INSERT INTO blog_likes (post_id, user_id) VALUES ($1, $2)",
                    post_id, user_id
                )
            else:
                 await conn.execute(
                    "INSERT INTO blog_likes (post_id, session_id) VALUES ($1, $2)",
                    post_id, session_id
                )

            new_count = post["likes_count"] + 1
            await conn.execute("UPDATE blog_posts SET likes_count = $1 WHERE id = $2", new_count, post_id)
            return BlogLikeResponse(likes_count=new_count, liked=True)

# -----------------------------------------------------------------------------
# COMMENTS (public)
# -----------------------------------------------------------------------------

@router.get("/{slug}/comments", response_model=List[BlogComment])
async def list_comments(slug: str):
    """List approved comments for a blog post."""
    async with get_connection() as conn:
        # Get post ID first
        post_id = await conn.fetchval("SELECT id FROM blog_posts WHERE slug = $1", slug)
        if not post_id:
             raise HTTPException(status_code=404, detail="Blog post not found")

        query = """
            SELECT c.*,
                   COALESCE(u.email, c.author_name, 'Anonymous') as author_name
            FROM blog_comments c
            LEFT JOIN users u ON c.user_id = u.id
            WHERE c.post_id = $1 AND c.status = 'approved'
            ORDER BY c.created_at ASC
        """
        rows = await conn.fetch(query, post_id)
        return [BlogComment(**row) for row in rows]

@router.post("/{slug}/comments", response_model=BlogComment)
async def create_comment(
    slug: str,
    comment: BlogCommentCreate,
    current_user: Optional[CurrentUser] = Depends(get_optional_user)
):
    """Create a new comment. Auto-approved for users, pending for guests."""
    async with get_connection() as conn:
        post = await conn.fetchrow("SELECT id FROM blog_posts WHERE slug = $1", slug)
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")

        status = CommentStatus.APPROVED if current_user else CommentStatus.PENDING
        user_id = current_user.id if current_user else None

        # If guest, author_name is required
        if not current_user and not comment.author_name:
             raise HTTPException(status_code=400, detail="Author name is required for guests")

        row = await conn.fetchrow(
            """
            INSERT INTO blog_comments (post_id, user_id, author_name, content, status)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, created_at, status, user_id, author_name, content, post_id
            """,
            post["id"], user_id, comment.author_name, comment.content, status.value
        )

        return BlogComment(**row)

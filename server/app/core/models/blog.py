from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, ConfigDict

class BlogStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class BlogPostBase(BaseModel):
    title: str
    slug: str
    content: str
    excerpt: Optional[str] = None
    cover_image: Optional[str] = None
    status: BlogStatus = BlogStatus.DRAFT
    tags: List[str] = []
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None

class BlogPostCreate(BlogPostBase):
    pass

class BlogPostUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    cover_image: Optional[str] = None
    status: Optional[BlogStatus] = None
    tags: Optional[List[str]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    published_at: Optional[datetime] = None

class BlogPost(BlogPostBase):
    id: UUID
    author_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    likes_count: int = 0
    created_at: datetime
    updated_at: datetime
    author_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class BlogPostResponse(BlogPost):
    liked_by_me: bool = False

class BlogListResponse(BaseModel):
    items: List[BlogPostResponse]
    total: int

class CommentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SPAM = "spam"

class BlogCommentBase(BaseModel):
    content: str
    author_name: Optional[str] = None

class BlogCommentCreate(BlogCommentBase):
    pass

class BlogComment(BlogCommentBase):
    id: UUID
    post_id: UUID
    user_id: Optional[UUID] = None
    status: CommentStatus
    created_at: datetime
    
    # Computed/Joined fields
    post_title: Optional[str] = None 

    model_config = ConfigDict(from_attributes=True)


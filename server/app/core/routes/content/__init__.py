"""content grouping folder — blog, news, newsletter, landing/media, SEO, misc marketing."""
from app.core.routes.content.blog import router as blog_router
from app.core.routes.content.hr_news import router as hr_news_router, public_router as hr_news_public_router
from app.core.routes.content.newsletter import (
    public_router as newsletter_public_router,
    admin_router as newsletter_admin_router,
)
from app.core.routes.content.landing_media import (
    public_router as landing_media_public_router,
    admin_router as landing_media_admin_router,
)
from app.core.routes.content.sitemap import router as sitemap_router
from app.core.routes.content.expert_advice import router as expert_advice_router
from app.core.routes.content.posters import router as posters_router
from app.core.routes.content.contact import router as contact_router

__all__ = [
    "blog_router",
    "hr_news_router",
    "hr_news_public_router",
    "newsletter_public_router",
    "newsletter_admin_router",
    "landing_media_public_router",
    "landing_media_admin_router",
    "sitemap_router",
    "expert_advice_router",
    "posters_router",
    "contact_router",
]

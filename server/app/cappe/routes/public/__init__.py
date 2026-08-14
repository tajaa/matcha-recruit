"""Cappe public surface — anonymous, by site slug.

Everything here is unauthenticated and reachable by any visitor, so each write
endpoint is (a) rate-limited per IP (layered minute+hour buckets), (b) guards
every email field against reserved/test domains, and (c) never trusts
client-supplied money/time — prices, order totals, and booking end-times are all
recomputed server-side. A site must be `published` to expose any public surface.

Split (2026-07-26) along the module's original banner comments into one file
per section; `_common.py` holds what's shared across more than one of them.
"""
from fastapi import APIRouter

from . import (
    blog,
    booking_suggestion_access,
    booking_selfserve,
    bookings,
    creators,
    directory,
    forms,
    messages,
    newsletter,
    reviews,
    shop,
    site,
)
from ._common import _validate_intake  # noqa: F401  (test_cappe_offerings imports this)

router = APIRouter()
router.include_router(site.router)
# Discover — the ONE endpoint here that returns many sites at once. It carries
# its own rate-limit bucket and depth cap; see the module docstring.
router.include_router(directory.router)
router.include_router(creators.router)
router.include_router(shop.router)
router.include_router(newsletter.router)
router.include_router(forms.router)
router.include_router(reviews.router)
router.include_router(booking_suggestion_access.router)
router.include_router(bookings.router)
router.include_router(bookings.suggestions_router)
router.include_router(booking_selfserve.router)
router.include_router(messages.router)
router.include_router(blog.router)

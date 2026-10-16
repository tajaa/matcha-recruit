/** Where "Start now" on the scheduling landing page goes: the self-serve
 *  signup for the scheduling product (an admin-composed product, so the slug
 *  is data — `product_definitions.slug`, managed at /admin/products).
 *
 *  Its price is read live from the same row (useSchedulingPrice), so a change
 *  at /admin/pricing shows here and at checkout together.
 *
 *  If that product is ever renamed, archived or replaced, this is the one
 *  line to change; the signup page itself shows "product not found" for a
 *  slug that is not published. */
export const SCHEDULING_PRODUCT_SLUG = 'schedule-comm'
export const SCHEDULING_SIGNUP_PATH = `/p/${SCHEDULING_PRODUCT_SLUG}/signup`

/** Where "Start now" on the scheduling landing page goes: the self-serve
 *  signup for the scheduling product (an admin-composed product, so the slug
 *  is data — `product_definitions.slug`, managed at /admin/products).
 *
 *  If that product is ever renamed, archived or replaced, this is the one
 *  line to change; the signup page itself shows "product not found" for a
 *  slug that is not published. */
export const SCHEDULING_SIGNUP_PATH = '/p/schedule-comm/signup'

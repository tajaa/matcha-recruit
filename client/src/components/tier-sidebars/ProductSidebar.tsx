import SidebarShell from '../sidebars/SidebarShell'
import type { NavItem } from '../sidebars/SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'
import { buildProductNav } from '../../data/productNavCatalog'
import type { ProductDefinition } from '../../types/dashboard'

/**
 * Sidebar for a tenant on an admin-composed product (/admin/products).
 *
 * There is no per-product component: the nav is derived from the product's own
 * granted features through PRODUCT_NAV_CATALOG (with the admin's optional
 * ordering/labels). Every row still carries its `feature` flag, so a row whose
 * flag was later revoked hides itself the same way it does in every other
 * sidebar.
 */
export default function ProductSidebar({ product }: { product: ProductDefinition }) {
  const { me, loading } = useMe()
  const { badges, markSeen } = useSidebarBadges()

  const items: NavItem[] = buildProductNav(product).map((entry) => {
    const item: NavItem = { to: entry.to, icon: entry.icon, label: entry.label }
    if (entry.to === '/app/ir') {
      return { ...item, badge: badges.ir || undefined, onSeen: () => markSeen('ir') }
    }
    return item
  })

  const footerName = me?.profile?.company_name

  return (
    <SidebarShell
      logoTo={items[0]?.to ?? '/app/company'}
      logoLabel={product.name}
      nav={loading ? [] : items}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}

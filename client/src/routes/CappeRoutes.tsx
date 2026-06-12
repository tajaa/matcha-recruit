import { Routes, Route } from 'react-router-dom'
import CappeLayout from '../layouts/CappeLayout'
import CappeSignup from '../pages/cappe/CappeSignup'
import CappeLogin from '../pages/cappe/CappeLogin'
import CappeSites from '../pages/cappe/CappeSites'
import CappeTemplates from '../pages/cappe/CappeTemplates'
import CappeSiteEditor from '../pages/cappe/CappeSiteEditor'

// Cappe — website-builder product, served at /cappe. A self-contained route
// tree with its own auth (cappe_* tokens, useCappeMe). The public signup/login
// live OUTSIDE the CappeLayout gate; everything else is behind it.
export default function CappeRoutes() {
  return (
    <Routes>
      <Route path="website-setup" element={<CappeSignup />} />
      <Route path="login" element={<CappeLogin />} />
      <Route element={<CappeLayout />}>
        <Route index element={<CappeSites />} />
        <Route path="templates" element={<CappeTemplates />} />
        <Route path="sites/:siteId" element={<CappeSiteEditor />} />
      </Route>
    </Routes>
  )
}

import { WorkRouteTree } from './WorkRouteTree'

// Matcha-Work — the business product surface (role='client', inside a Matcha
// company), served at /work. The tree itself lives in WorkRouteTree, shared
// with the personal /werk surface.
export default function WorkRoutes() {
  return <WorkRouteTree surface="matcha-work" />
}

import { WorkRouteTree } from './WorkRouteTree'

// Werk — the personal product surface (role='individual'), served at /werk.
// Same tree as the business /work surface; the surface value drives branding
// and nav base paths.
export default function WerkRoutes() {
  return <WorkRouteTree surface="werk" />
}

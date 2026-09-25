import { WorkRouteTree } from './WorkRouteTree'

// Espresso — the personal product surface (role='individual'), served at /espresso.
// Same tree as the business /work surface; the surface value drives branding
// and nav base paths.
export default function EspressoRoutes() {
  return <WorkRouteTree surface="espresso" />
}

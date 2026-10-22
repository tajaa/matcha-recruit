import { useParams } from 'react-router-dom'
import SurfaceShell from '../../components/SurfaceShell'
import LibraryPanel from './LibraryPanel'

/** `sites/:siteId/library` — the site's pictures and what is printed beside
 *  each one (alt text, caption, credit). */
export default function LibraryPage() {
  const { siteId } = useParams<{ siteId: string }>()
  if (!siteId) return null
  return (
    <SurfaceShell
      title="Library"
      subtitle="Your pictures, with the alt text, caption and credit printed beside them."
    >
      <LibraryPanel siteId={siteId} />
    </SurfaceShell>
  )
}

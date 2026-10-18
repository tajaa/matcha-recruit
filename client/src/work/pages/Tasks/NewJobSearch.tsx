import type { JobSearchSummary } from '../../api/matchaWork/jobSearch'
import { useJobSearch } from '../JobSearch/useJobSearch'
import NewJobSearchModal from '../JobSearch/NewJobSearchModal'

/** Only mounted while open: loading the form checks Job search entitlement. */
export default function NewJobSearch({ onCreated, onClose }: {
  onCreated: (search: JobSearchSummary) => void
  onClose: () => void
}) {
  const js = useJobSearch(undefined, null)
  return (
    <NewJobSearchModal
      list={js.list}
      loadError={js.listError}
      onRetry={() => void js.loadList()}
      onCreate={js.create}
      onCreated={onCreated}
      onClose={onClose}
    />
  )
}

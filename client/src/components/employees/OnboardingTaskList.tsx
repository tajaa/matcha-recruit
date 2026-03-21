import { useRef, useState } from 'react'
import { Badge, Button } from '../ui'
import { useOnboardingTasks } from '../../hooks/employees/useOnboardingTasks'
import { useCredentialDocuments } from '../../hooks/employees/useCredentialDocuments'
import type { OnboardingTask } from '../../types/employee'

const categoryLabel: Record<string, string> = {
  documents: 'Documents',
  equipment: 'Equipment',
  training: 'Training',
  admin: 'Admin',
  return_to_work: 'Return to Work',
  credentials: 'Credentials',
}

const statusVariant = {
  completed: 'success',
  skipped: 'neutral',
  pending: 'warning',
} as const

function CredentialUploadButton({
  employeeId,
  documentType,
  onUploaded,
}: {
  employeeId: string
  documentType: string
  onUploaded: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { upload } = useCredentialDocuments(employeeId)
  const [uploading, setUploading] = useState(false)

  const handleFile = async (file: File) => {
    setUploading(true)
    try {
      await upload(file, documentType)
      onUploaded()
    } finally {
      setUploading(false)
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.gif,.tiff"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ''
        }}
      />
      <Button
        size="sm"
        variant="primary"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? 'Uploading...' : 'Upload'}
      </Button>
    </>
  )
}

export function OnboardingTaskList({ employeeId }: { employeeId: string }) {
  const { tasks, loading, updateTask, refetch } = useOnboardingTasks(employeeId)

  if (loading) return <p className="text-xs text-zinc-500">Loading tasks...</p>
  if (tasks.length === 0) return <p className="text-xs text-zinc-500">No onboarding tasks.</p>

  const completed = tasks.filter((t) => t.status === 'completed').length
  const groups = tasks.reduce<Record<string, OnboardingTask[]>>((acc, t) => {
    const cat = t.category || 'admin'
    ;(acc[cat] ??= []).push(t)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {/* Progress */}
      <div>
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-1">
          <span>Progress</span>
          <span>{completed} of {tasks.length} completed</span>
        </div>
        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${tasks.length ? (completed / tasks.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Grouped tasks */}
      {Object.entries(groups).map(([category, catTasks]) => (
        <div key={category}>
          <h4 className="text-xs font-medium text-zinc-400 mb-2">
            {categoryLabel[category] ?? category}
          </h4>
          <div className="space-y-2">
            {catTasks.map((t) => (
              <div key={t.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200">{t.title}</p>
                  {t.due_date && (
                    <p className="text-[10px] text-zinc-500 mt-0.5">
                      Due {new Date(t.due_date).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <Badge variant={statusVariant[t.status as keyof typeof statusVariant] ?? 'neutral'}>
                  {t.status}
                </Badge>
                {t.status === 'pending' && (
                  <div className="flex gap-1">
                    {t.category === 'credentials' && t.document_type ? (
                      <CredentialUploadButton
                        employeeId={employeeId}
                        documentType={t.document_type}
                        onUploaded={refetch}
                      />
                    ) : (
                      <Button size="sm" variant="ghost"
                        onClick={() => updateTask(t.id, { status: 'completed' })}>
                        Complete
                      </Button>
                    )}
                    <Button size="sm" variant="ghost"
                      onClick={() => updateTask(t.id, { status: 'skipped' })}>
                      Skip
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

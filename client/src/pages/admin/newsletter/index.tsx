import { useNavigate } from 'react-router-dom'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../../../api/client'
import type { Tag } from './types'
import { SubscribersTab } from './SubscribersTab'
import { NewslettersTab } from './NewslettersTab'
import { ComposeTab } from './ComposeTab'
import { TagsTab } from './TagsTab'
import { TemplatesTab } from './TemplatesTab'
import { IdeasTab } from './IdeasTab'
import { SendModal } from './SendModal'
import { AnalyticsDrawer } from './AnalyticsDrawer'
import { CsvImportModal } from './CsvImportModal'
import { useNewsletterAdmin } from './useNewsletterAdmin'
import { NewsletterStatsBar } from './NewsletterStatsBar'
import { SendProgressBanner } from './SendProgressBanner'
import { NewsletterTabsNav } from './NewsletterTabsNav'

export default function NewsletterAdmin() {
  const navigate = useNavigate()
  const {
    tab,
    subscribers, stats, newsletters, tags, setTags, templates, ideas, growth,
    loading, search, setSearch,
    composeTitle, setComposeTitle,
    composeSubject, setComposeSubject,
    composePreheader, setComposePreheader,
    composeHtml, setComposeHtml,
    composeMode, setComposeMode,
    composeDesign, setComposeDesign,
    editingId, saving, isDirty, setIsDirty,
    saveStatus, setSaveStatus,
    previewViewport, setPreviewViewport,
    sendModal, setSendModal,
    sendSegmentTags, setSendSegmentTags,
    sendScheduledAt, setSendScheduledAt,
    sending, progress,
    analyticsOpen, setAnalyticsOpen, analytics,
    importOpen, setImportOpen,
    managingTagsFor, setManagingTagsFor,
    subTagsCache, filteredSubs,
    loadData, upsertNewsletter,
    handleCreate, handleSave, openSend, confirmSend, handleTestSend,
    handleDelete, handleDeleteSubscriber, handleExport,
    startEdit, startFromDesign, fromTemplate, openAnalytics,
    loadSubTags, toggleSubTag, handleTabChange,
  } = useNewsletterAdmin()

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-500" size={24} /></div>
  }

  return (
    <div>
      <div className="rounded-xl border border-white/[0.06] bg-zinc-950 p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Newsletter</h1>
        <button
          onClick={() => {
            if (isDirty && !confirm('Discard unsaved changes?')) return
            navigate('/admin/newsletter/composer')
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
        >
          <Plus size={14} /> New Newsletter
        </button>
      </div>

      {/* Stats + growth sparkline */}
      {stats && <NewsletterStatsBar stats={stats} growth={growth} />}

      {/* Send progress (sticky banner while sending) */}
      {progress && progress.newsletter_status === 'sending' && (
        <SendProgressBanner progress={progress} />
      )}

      {/* Tabs */}
      <NewsletterTabsNav tab={tab} editingId={editingId} newsletters={newsletters} onTabChange={handleTabChange} />

      {/* Ideas scratchpad tab */}
      {tab === 'ideas' && (
        <IdeasTab
          ideas={ideas}
          onChange={loadData}
          onCreatedNewsletter={(nl) => { upsertNewsletter(nl); startEdit(nl) }}
        />
      )}

      {/* Subscribers tab */}
      {tab === 'subscribers' && (
        <SubscribersTab
          search={search} onSearchChange={setSearch}
          filteredSubs={filteredSubs}
          tags={tags}
          subTagsCache={subTagsCache}
          managingTagsFor={managingTagsFor} onManagingTagsForChange={setManagingTagsFor}
          onImportOpen={() => setImportOpen(true)}
          onExport={handleExport}
          onLoadSubTags={loadSubTags}
          onToggleSubTag={toggleSubTag}
          onDeleteSubscriber={handleDeleteSubscriber}
        />
      )}

      {/* Newsletters tab */}
      {tab === 'newsletters' && (
        <NewslettersTab
          newsletters={newsletters}
          onEdit={startEdit}
          onDelete={handleDelete}
          onOpenAnalytics={openAnalytics}
          onReload={loadData}
        />
      )}

      {/* Compose tab — split editor + mobile preview */}
      {tab === 'compose' && (
        <ComposeTab
          saveStatus={saveStatus}
          editingId={editingId}
          composeTitle={composeTitle} setComposeTitle={setComposeTitle}
          composeSubject={composeSubject} setComposeSubject={setComposeSubject}
          composePreheader={composePreheader} setComposePreheader={setComposePreheader}
          composeHtml={composeHtml} setComposeHtml={setComposeHtml}
          composeMode={composeMode} setComposeMode={setComposeMode}
          composeDesign={composeDesign} setComposeDesign={setComposeDesign}
          setIsDirty={setIsDirty} setSaveStatus={setSaveStatus}
          previewViewport={previewViewport} setPreviewViewport={setPreviewViewport}
          saving={saving}
          handleCreate={handleCreate}
          handleSave={handleSave}
          handleTestSend={handleTestSend}
          openSend={openSend}
        />
      )}

      {/* Tags tab */}
      {tab === 'tags' && <TagsTab tags={tags} onChange={async () => { const t = await api.get<{ tags: Tag[] }>('/admin/newsletter/tags'); setTags(t.tags) }} subscribers={subscribers} />}

      {/* Templates tab */}
      {tab === 'templates' && <TemplatesTab templates={templates} onChange={loadData} onPickTemplate={fromTemplate} onStartFrom={startFromDesign} currentDesign={composeDesign} />}
      </div>

      {/* Send modal */}
      {sendModal && (
        <SendModal
          sendModal={sendModal} setSendModal={setSendModal}
          tags={tags} stats={stats}
          sendSegmentTags={sendSegmentTags} setSendSegmentTags={setSendSegmentTags}
          sendScheduledAt={sendScheduledAt} setSendScheduledAt={setSendScheduledAt}
          sending={sending} confirmSend={confirmSend}
        />
      )}

      {/* Analytics drawer */}
      {analyticsOpen && (
        <AnalyticsDrawer setAnalyticsOpen={setAnalyticsOpen} analytics={analytics} />
      )}

      {importOpen && <CsvImportModal onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); loadData() }} />}
    </div>
  )
}

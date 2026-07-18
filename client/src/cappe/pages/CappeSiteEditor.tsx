import { Link } from 'react-router-dom'
import { Loader2, ArrowLeft } from 'lucide-react'
import SetupGuide from '../components/SetupGuide'
import { cappeSiteHost } from '../host'
import { useCappeSiteEditor } from './CappeSiteEditor/useCappeSiteEditor'
import { EditorHeader } from './CappeSiteEditor/EditorHeader'
import { SettingsSection } from './CappeSiteEditor/SettingsSection'
import { BusinessInfoSection } from './CappeSiteEditor/BusinessInfoSection'
import { DesignSection } from './CappeSiteEditor/DesignSection'
import { PagesSection } from './CappeSiteEditor/PagesSection'

export default function CappeSiteEditor() {
  const s = useCappeSiteEditor()

  if (s.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </div>
    )
  }

  if (!s.site) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <p className="text-sm text-red-400">{s.error || 'Site not found.'}</p>
        <Link to="/cappe/sites" className="mt-4 inline-flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
          <ArrowLeft className="h-4 w-4" /> Back to sites
        </Link>
      </div>
    )
  }

  const publicUrl = cappeSiteHost(s.site)

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <EditorHeader site={s.site} publicUrl={publicUrl} publishing={s.publishing} onPublish={s.publish} />

      {s.error && <p className="mb-4 text-sm text-red-400">{s.error}</p>}
      {s.notice && <p className="mb-4 text-sm text-emerald-400">{s.notice}</p>}

      <SetupGuide site={s.site} pages={s.pages} publishing={s.publishing} onPublish={s.publish} refreshKey={s.setupRefresh} />

      {/* Settings */}
      <SettingsSection
        siteId={s.siteId || ''}
        name={s.name}
        setName={s.setName}
        subdomain={s.subdomain}
        setSubdomain={s.setSubdomain}
        timezone={s.timezone}
        setTimezone={s.setTimezone}
        logo={s.logo}
        setLogo={s.setLogo}
        saving={s.saving}
        onSave={s.save}
      />

      {/* Business info, social, SEO */}
      <BusinessInfoSection
        site={s.site}
        siteId={s.siteId || ''}
        biz={s.biz}
        setBiz={s.setBiz}
        saving={s.saving}
        onSave={s.save}
      />

      {/* Design / theme */}
      <DesignSection site={s.site} themeBusy={s.themeBusy} onApplyTheme={s.applyTheme} />

      {/* Pages */}
      <PagesSection
        siteId={s.siteId || ''}
        pages={s.pages}
        newPageTitle={s.newPageTitle}
        setNewPageTitle={s.setNewPageTitle}
        addingPage={s.addingPage}
        onAddPage={s.addPage}
        onAddPreset={s.addPreset}
        onDeletePage={s.deletePage}
      />

      <button onClick={s.deleteSite} className="text-sm text-red-400 hover:text-red-300">
        Delete site
      </button>
    </div>
  )
}

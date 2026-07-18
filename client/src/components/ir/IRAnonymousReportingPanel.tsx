import { useAnonymousReporting } from './IRAnonymousReportingPanel/useAnonymousReporting'
import { CompanyWideSection } from './IRAnonymousReportingPanel/CompanyWideSection'
import { BrandingSection } from './IRAnonymousReportingPanel/BrandingSection'
import { LocationLinksSection } from './IRAnonymousReportingPanel/LocationLinksSection'

export function IRAnonymousReportingPanel() {
  const s = useAnonymousReporting()

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl">
      <div className="px-5 py-3 border-b border-white/5">
        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Anonymous Reporting</span>
      </div>
      <div className="p-5 space-y-5">
        {/* Company-wide anonymous link */}
        <CompanyWideSection
          status={s.status}
          loading={s.loading}
          generateLink={s.generateLink}
          disable={s.disable}
          downloadPoster={s.downloadPoster}
        />

        <div className="border-t border-white/5" />

        {/* QR poster branding — customize colors; Matcha branding stays fixed */}
        <BrandingSection
          branding={s.branding}
          brandingLoading={s.brandingLoading}
          brandingSaving={s.brandingSaving}
          brandingDirty={s.brandingDirty}
          brandingSaved={s.brandingSaved}
          updateBrand={s.updateBrand}
          resetBranding={s.resetBranding}
          saveBranding={s.saveBranding}
        />

        <div className="border-t border-white/5" />

        {/* Per-location magic links */}
        <LocationLinksSection
          locations={s.locations}
          links={s.links}
          pickable={s.pickable}
          pickLoc={s.pickLoc}
          setPickLoc={s.setPickLoc}
          genLoading={s.genLoading}
          generateForLocation={s.generateForLocation}
          genMaxUses={s.genMaxUses}
          setGenMaxUses={s.setGenMaxUses}
          genExpiry={s.genExpiry}
          setGenExpiry={s.setGenExpiry}
          linkSearch={s.linkSearch}
          setLinkSearch={s.setLinkSearch}
          linkQuery={s.linkQuery}
          activeLinks={s.activeLinks}
          inactiveLinks={s.inactiveLinks}
          inactiveOpen={s.inactiveOpen}
          setInactiveOpen={s.setInactiveOpen}
          qrOpen={s.qrOpen}
          setQrOpen={s.setQrOpen}
          histOpen={s.histOpen}
          histData={s.histData}
          toggleHistory={s.toggleHistory}
          revokeLink={s.revokeLink}
          downloadPoster={s.downloadPoster}
        />
      </div>
    </div>
  )
}

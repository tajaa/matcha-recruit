import { memo, useState } from 'react';

import type { MWDocumentState } from '../../types/matcha-work';

interface HandbookPreviewProps {
  state: MWDocumentState;
  onRender?: () => void;
}

const HANDBOOK_PROFILE_LABELS: [string, string][] = [
  ['remote_workers', 'Remote Workers'],
  ['minors', 'Minors'],
  ['tipped_employees', 'Tipped Employees'],
  ['tip_pooling', 'Tip Pooling'],
  ['union_employees', 'Union Employees'],
  ['federal_contracts', 'Federal Contracts'],
  ['group_health_insurance', 'Group Health Insurance'],
  ['background_checks', 'Background Checks'],
  ['hourly_employees', 'Hourly Employees'],
  ['salaried_employees', 'Salaried Employees'],
  ['commissioned_employees', 'Commissioned Employees'],
];

const GREEN_FLAGS_COLLAPSED_LIMIT = 6;

function UploadBranch({ state }: { state: MWDocumentState }) {
  const [greenExpanded, setGreenExpanded] = useState(false);

  const title = state.handbook_title || 'Employee Handbook';
  const uploadStatus = state.handbook_upload_status || 'idle';
  const uploadedFilename = state.handbook_uploaded_filename || '';
  const blockingError = state.handbook_blocking_error || '';
  const reviewLocations = state.handbook_review_locations || [];
  const redFlags = state.handbook_red_flags || [];
  const greenFlags = state.handbook_green_flags || [];
  const jurisdictionSummaries = state.handbook_jurisdiction_summaries || [];
  const mode = state.handbook_mode || '';
  const sections = state.handbook_sections || [];
  const strengthScore = state.handbook_strength_score;
  const strengthLabel = state.handbook_strength_label || '';

  const severityCounts = redFlags.reduce(
    (acc, flag) => {
      const severity = flag.severity || 'medium';
      if (severity in acc) acc[severity as 'high' | 'medium' | 'low'] += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );

  const uploadStatusColor =
    uploadStatus === 'reviewed' ? 'text-green-400 bg-green-400/10' :
    uploadStatus === 'analyzing' || uploadStatus === 'uploading' ? 'text-orange-400 bg-orange-400/10' :
    uploadStatus === 'blocked' || uploadStatus === 'error' ? 'text-red-400 bg-red-400/10' :
    'text-zinc-400 bg-zinc-400/10';

  const severityBadgeClasses = (severity: 'high' | 'medium' | 'low') =>
    severity === 'high'
      ? 'text-red-300 bg-red-500/10 border border-red-500/20'
      : severity === 'medium'
        ? 'text-orange-300 bg-orange-500/10 border border-orange-500/20'
        : 'text-sky-300 bg-sky-500/10 border border-sky-500/20';

  const scoreColor = strengthScore == null ? 'text-zinc-400' :
    strengthScore >= 80 ? 'text-green-400' :
    strengthScore >= 50 ? 'text-orange-400' : 'text-red-400';

  const scoreTrackColor = strengthScore == null ? 'stroke-zinc-700' :
    strengthScore >= 80 ? 'stroke-green-400/20' :
    strengthScore >= 50 ? 'stroke-orange-400/20' : 'stroke-red-400/20';

  const scoreStrokeColor = strengthScore == null ? 'stroke-zinc-400' :
    strengthScore >= 80 ? 'stroke-green-400' :
    strengthScore >= 50 ? 'stroke-orange-400' : 'stroke-red-400';

  const visibleGreen = greenExpanded ? greenFlags : greenFlags.slice(0, GREEN_FLAGS_COLLAPSED_LIMIT);

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-3xl mx-auto space-y-4">
        {/* Header */}
        <div>
          <h2 className="text-lg font-bold text-zinc-100 light:text-zinc-900 tracking-tight">{title}</h2>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="text-[11px] font-medium text-zinc-300 light:text-zinc-600 px-2 py-0.5 bg-zinc-800 light:bg-zinc-200/60">
              Uploaded Handbook
            </span>
            {mode && (
              <span className="text-[11px] font-medium text-zinc-300 light:text-zinc-600 px-2 py-0.5 bg-zinc-800 light:bg-zinc-200/60">
                {mode === 'multi_state' ? 'Multi-State' : 'Single State'}
              </span>
            )}
            <span className={`text-[11px] font-medium px-2 py-0.5 ${uploadStatusColor}`}>
              {uploadStatus.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
            </span>
          </div>
        </div>

        {/* Source file */}
        {uploadedFilename && (
          <div className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Source File</p>
            <p className="mt-1 text-sm text-zinc-200 light:text-zinc-800">{uploadedFilename}</p>
            {state.handbook_analysis_generated_at && (
              <p className="mt-1 text-[11px] text-zinc-500">
                Reviewed {new Date(state.handbook_analysis_generated_at).toLocaleString()}
              </p>
            )}
          </div>
        )}

        {/* Blocking error */}
        {blockingError && (
          <div className="flex items-start gap-2 p-3 bg-red-400/10 border border-red-400/20">
            <svg className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <p className="text-xs text-red-300 leading-relaxed">{blockingError}</p>
          </div>
        )}

        {/* Coverage Score ring gauge */}
        {strengthScore != null && (
          <div className="flex items-center gap-3 bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
            <svg width="44" height="44" viewBox="0 0 44 44" className="flex-shrink-0">
              <circle cx="22" cy="22" r="18" fill="none" strokeWidth="4" className={scoreTrackColor} />
              <circle
                cx="22" cy="22" r="18" fill="none" strokeWidth="4"
                className={scoreStrokeColor}
                strokeLinecap="round"
                strokeDasharray={`${(strengthScore / 100) * 113.1} 113.1`}
                transform="rotate(-90 22 22)"
              />
              <text x="22" y="22" textAnchor="middle" dominantBaseline="central" className={`text-[13px] font-bold font-mono fill-current ${scoreColor}`}>
                {strengthScore}
              </text>
            </svg>
            <div>
              <p className="text-xs text-zinc-500 font-medium">Coverage Score</p>
              <p className={`text-sm font-semibold ${scoreColor}`}>{strengthLabel}</p>
            </div>
          </div>
        )}

        {/* Severity count cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(['high', 'medium', 'low'] as const).map((severity) => (
            <div key={severity} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">{severity}</p>
              <p className="mt-1 text-xl font-semibold text-zinc-100 light:text-zinc-900">{severityCounts[severity]}</p>
            </div>
          ))}
        </div>

        {/* Per-Jurisdiction Summary Cards */}
        {jurisdictionSummaries.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">Jurisdiction Coverage</p>
            {jurisdictionSummaries.map((js) => {
              const ratio = js.total_count > 0 ? js.covered_count / js.total_count : 0;
              const ratioColor = ratio >= 0.8 ? 'text-green-400' : ratio >= 0.5 ? 'text-orange-400' : 'text-red-400';
              const barColor = ratio >= 0.8 ? 'bg-green-400' : ratio >= 0.5 ? 'bg-orange-400' : 'bg-red-400';
              return (
                <div key={js.location_label} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-zinc-100 light:text-zinc-900">{js.location_label}</p>
                    <span className={`text-sm font-bold font-mono ${ratioColor}`}>{js.covered_count}/{js.total_count}</span>
                  </div>
                  <div className="h-1.5 bg-zinc-700 light:bg-zinc-300 overflow-hidden">
                    <div className={`h-full ${barColor} transition-all`} style={{ width: `${ratio * 100}%` }} />
                  </div>
                  {js.covered_categories.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {js.covered_categories.map((cat) => (
                        <span key={cat} className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-300 border border-green-500/20">
                          {cat.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                  {js.missing_categories.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {js.missing_categories.map((cat) => (
                        <span key={cat} className="text-[10px] px-1.5 py-0.5 bg-red-500/10 text-red-300 border border-red-500/20">
                          {cat.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Red Flags */}
        {redFlags.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">Red Flags</p>
            {redFlags.map((flag) => (
              <div key={flag.id} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3 space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-zinc-100 light:text-zinc-900">{flag.section_title}</p>
                    <p className="text-[11px] text-zinc-500">{flag.jurisdiction}</p>
                  </div>
                  <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 ${severityBadgeClasses(flag.severity)}`}>
                    {flag.severity}
                  </span>
                </div>
                <p className="text-sm text-zinc-200 light:text-zinc-800">{flag.summary}</p>
                <p className="text-xs text-zinc-400 light:text-zinc-600 leading-relaxed">{flag.why_it_matters}</p>
                <p className="text-xs text-zinc-300 light:text-zinc-700 leading-relaxed">
                  <span className="text-zinc-500">Recommended action:</span> {flag.recommended_action}
                </p>
              </div>
            ))}
          </div>
        ) : uploadStatus === 'reviewed' ? (
          <div className="bg-green-500/10 border border-green-500/20 p-3">
            <p className="text-xs text-green-300 leading-relaxed">
              No jurisdiction coverage gaps detected.{greenFlags.length > 0 ? ` ${greenFlags.length} compliance requirement(s) confirmed covered.` : ''} Review the parsed sections below for details.
            </p>
          </div>
        ) : null}

        {/* Green Flags — Covered Requirements */}
        {greenFlags.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">Covered Requirements</p>
            {visibleGreen.map((flag) => (
              <div key={flag.id} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-green-500/10 light:border-green-200 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-zinc-100 light:text-zinc-900">{flag.category_label}</p>
                    <p className="text-[11px] text-zinc-500">{flag.jurisdiction}</p>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 text-green-300 bg-green-500/10 border border-green-500/20">
                    covered
                  </span>
                </div>
                <p className="text-xs text-zinc-400 light:text-zinc-600 mt-1 leading-relaxed">{flag.summary}</p>
              </div>
            ))}
            {greenFlags.length > GREEN_FLAGS_COLLAPSED_LIMIT && (
              <button
                onClick={() => setGreenExpanded(!greenExpanded)}
                className="text-xs text-matcha-400 hover:text-matcha-300 font-medium transition-colors"
              >
                {greenExpanded ? 'Show less' : `Show all ${greenFlags.length} covered requirements`}
              </button>
            )}
          </div>
        )}

        {/* Parsed Sections */}
        {sections.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">Parsed Sections</p>
            {sections.map((section) => (
              <div key={section.section_key} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
                <p className="text-sm font-medium text-zinc-200 light:text-zinc-800">{section.title}</p>
                {section.content && (
                  <p className="text-xs text-zinc-400 light:text-zinc-600 mt-1 line-clamp-4 leading-relaxed">{section.content}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function HandbookPreviewComponent({ state, onRender }: HandbookPreviewProps) {
  onRender?.();
  const title = state.handbook_title || 'Employee Handbook';
  const status = state.handbook_status || 'collecting';
  const sourceType = state.handbook_source_type || 'template';
  const uploadStatus = state.handbook_upload_status || 'idle';
  const uploadedFilename = state.handbook_uploaded_filename || '';
  const blockingError = state.handbook_blocking_error || '';
  const reviewLocations = state.handbook_review_locations || [];
  const redFlags = state.handbook_red_flags || [];
  const mode = state.handbook_mode || '';
  const industry = state.handbook_industry || '';
  const subIndustry = state.handbook_sub_industry || '';
  const legalName = state.handbook_legal_name || '';
  const dba = state.handbook_dba || '';
  const ceo = state.handbook_ceo || '';
  const headcount = state.handbook_headcount;
  const errorMessage = state.handbook_error || '';
  const strengthScore = state.handbook_strength_score;
  const strengthLabel = state.handbook_strength_label || '';
  const states = state.handbook_states || [];
  const sections = state.handbook_sections || [];

  if (sourceType === 'upload') {
    return <UploadBranch state={state} />;
  }

  const profileFlags: [string, boolean][] = [];
  if (state.handbook_profile) {
    for (const [key, label] of HANDBOOK_PROFILE_LABELS) {
      const val = (state.handbook_profile as Record<string, boolean | undefined>)[key];
      if (val !== undefined) {
        profileFlags.push([label, val]);
      }
    }
  }

  let requiredFilled = 0;
  if (title && title !== 'Employee Handbook') requiredFilled++;
  if (states.length > 0) requiredFilled++;
  if (legalName) requiredFilled++;
  if (ceo) requiredFilled++;

  const statusColor =
    status === 'created' ? 'text-green-400 bg-green-400/10' :
    status === 'generating' ? 'text-orange-400 bg-orange-400/10' :
    status === 'error' ? 'text-red-400 bg-red-400/10' :
    status === 'ready' ? 'text-blue-400 bg-blue-400/10' :
    'text-zinc-400 bg-zinc-400/10';

  const scoreColor = !strengthScore ? 'text-zinc-400' :
    strengthScore >= 80 ? 'text-green-400' :
    strengthScore >= 50 ? 'text-orange-400' : 'text-red-400';

  const scoreTrackColor = !strengthScore ? 'stroke-zinc-700' :
    strengthScore >= 80 ? 'stroke-green-400/20' :
    strengthScore >= 50 ? 'stroke-orange-400/20' : 'stroke-red-400/20';

  const scoreStrokeColor = !strengthScore ? 'stroke-zinc-400' :
    strengthScore >= 80 ? 'stroke-green-400' :
    strengthScore >= 50 ? 'stroke-orange-400' : 'stroke-red-400';

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 light:text-zinc-900 tracking-tight">{title}</h2>
          <div className="flex items-center gap-2 mt-1.5">
            {mode && (
              <span className="text-[11px] font-medium text-zinc-300 light:text-zinc-600 px-2 py-0.5 bg-zinc-800 light:bg-zinc-200/60">
                {mode === 'multi_state' ? 'Multi-State' : 'Single State'}
              </span>
            )}
            <span className={`text-[11px] font-medium px-2 py-0.5 ${statusColor}`}>
              {status.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
            </span>
          </div>
        </div>

        {errorMessage && (
          <div className="flex items-start gap-2 p-3 bg-red-400/10 border border-red-400/20">
            <svg className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <p className="text-xs text-red-300 leading-relaxed">{errorMessage}</p>
          </div>
        )}

        {states.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <svg className="w-3.5 h-3.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            {states.map((st) => (
              <span key={st} className="text-[11px] font-semibold font-mono text-white px-2 py-0.5 bg-blue-500/20 border border-blue-500/20">
                {st}
              </span>
            ))}
          </div>
        )}

        {industry && (
          <div className="flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            <span className="text-sm text-zinc-200 light:text-zinc-700">{industry.charAt(0).toUpperCase() + industry.slice(1)}</span>
            {subIndustry && <span className="text-xs text-zinc-500">({subIndustry})</span>}
          </div>
        )}

        {(legalName || ceo) && (
          <div className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3 space-y-1.5">
            {legalName && (
              <div className="flex gap-2 text-xs"><span className="text-zinc-500 font-medium w-20 flex-shrink-0">Legal Name</span><span className="text-zinc-200 light:text-zinc-800">{legalName}</span></div>
            )}
            {dba && (
              <div className="flex gap-2 text-xs"><span className="text-zinc-500 font-medium w-20 flex-shrink-0">DBA</span><span className="text-zinc-200 light:text-zinc-800">{dba}</span></div>
            )}
            {ceo && (
              <div className="flex gap-2 text-xs"><span className="text-zinc-500 font-medium w-20 flex-shrink-0">CEO</span><span className="text-zinc-200 light:text-zinc-800">{ceo}</span></div>
            )}
            {headcount != null && (
              <div className="flex gap-2 text-xs"><span className="text-zinc-500 font-medium w-20 flex-shrink-0">Headcount</span><span className="text-zinc-200 light:text-zinc-800">{headcount}</span></div>
            )}
          </div>
        )}

        {profileFlags.length > 0 && (
          <div className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3 space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">Company Profile</p>
            <div className="grid grid-cols-2 gap-1.5">
              {profileFlags.map(([label, enabled]) => (
                <div key={label} className="flex items-center gap-1.5">
                  {enabled ? (
                    <svg className="w-3.5 h-3.5 text-green-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" /></svg>
                  ) : (
                    <svg className="w-3.5 h-3.5 text-zinc-600" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" /></svg>
                  )}
                  <span className={`text-[11px] ${enabled ? 'text-zinc-200 light:text-zinc-700' : 'text-zinc-500'}`}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {status !== 'created' && status !== 'error' && (
          <div className="space-y-1.5">
            <p className="text-xs text-zinc-500 font-medium">Required Fields ({requiredFilled}/4)</p>
            <div className="h-1.5 bg-zinc-800 light:bg-zinc-200 overflow-hidden">
              <div
                className={`h-full transition-all ${requiredFilled === 4 ? 'bg-green-400' : 'bg-matcha-500'}`}
                style={{ width: `${(requiredFilled / 4) * 100}%` }}
              />
            </div>
          </div>
        )}

        {strengthScore != null && (
          <div className="flex items-center gap-3 bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
            <svg width="44" height="44" viewBox="0 0 44 44" className="flex-shrink-0">
              <circle cx="22" cy="22" r="18" fill="none" strokeWidth="4" className={scoreTrackColor} />
              <circle
                cx="22"
                cy="22"
                r="18"
                fill="none"
                strokeWidth="4"
                className={scoreStrokeColor}
                strokeLinecap="round"
                strokeDasharray={`${(strengthScore / 100) * 113.1} 113.1`}
                transform="rotate(-90 22 22)"
              />
              <text x="22" y="22" textAnchor="middle" dominantBaseline="central" className={`text-[13px] font-bold font-mono fill-current ${scoreColor}`}>
                {strengthScore}
              </text>
            </svg>
            <div>
              <p className="text-xs text-zinc-500 font-medium">Coverage Score</p>
              <p className={`text-sm font-semibold ${scoreColor}`}>{strengthLabel}</p>
            </div>
          </div>
        )}

        {sections.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-zinc-200 light:text-zinc-800 uppercase tracking-wider">{sections.length} Sections</p>
            {sections.map((section) => (
              <div key={section.section_key} className="bg-zinc-800/60 light:bg-zinc-100/60 border border-white/10 light:border-zinc-200 p-3">
                <p className="text-sm font-medium text-zinc-200 light:text-zinc-800">{section.title}</p>
                {section.content && (
                  <p className="text-xs text-zinc-400 light:text-zinc-600 mt-1 line-clamp-3 leading-relaxed">{section.content}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

HandbookPreviewComponent.displayName = 'HandbookPreview';

export const HandbookPreview = memo(HandbookPreviewComponent);

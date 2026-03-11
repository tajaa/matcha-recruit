import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import type {
  MWMessage,
  MWThreadDetail,
  MWDocumentState,
  MWDocumentVersion,
  MWTokenUsage,
  MWUsageSummaryResponse,
  MWReviewRequestStatus,
} from '../types/matcha-work';
import type { CurrentUserResponse, HandbookListItem } from '../types';
import { ApiRequestError, handbooks, matchaWork, adminPlatformSettings, getAccessToken } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { HandbookPreview } from '../components/matcha-work/HandbookPreview';
import { HandbookUpload } from '../components/matcha-work/HandbookUpload';
import { LogoUpload } from '../components/matcha-work/LogoUpload';
import HandbookDistributeModal from '../components/HandbookDistributeModal';

type Tab = 'chat' | 'preview';
type PreviewKind = 'offer_letter' | 'presentation' | 'workbook' | 'handbook' | 'policy' | 'onboarding' | 'review' | null;

function toItemList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter((item) => item.length > 0);
  }
  if (typeof value === 'string') {
    return value
      .split(/\n|;/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  return [];
}

function hasWorkbookState(state?: MWDocumentState | null): boolean {
  return Boolean(
    state?.workbook_title ||
    state?.company_name ||
    state?.objective ||
    state?.industry ||
    (state?.sections && state.sections.length > 0) ||
    (state?.presentation && state.presentation.slides?.length > 0)
  );
}

function hasReviewState(state?: MWDocumentState | null): boolean {
  return Boolean(
    state?.review_title ||
    state?.review_subject ||
    state?.summary ||
    state?.context ||
    state?.next_steps ||
    toItemList(state?.strengths).length > 0 ||
    toItemList(state?.growth_areas).length > 0 ||
    (state?.review_request_statuses && state.review_request_statuses.length > 0)
  );
}

function hasOnboardingState(state?: MWDocumentState | null): boolean {
  return Boolean(
    (state?.employees && state.employees.length > 0) ||
    state?.batch_status
  );
}

function hasPresentationState(state?: MWDocumentState | null): boolean {
  return Boolean(
    state?.presentation_title ||
    (state?.slides && state.slides.length > 0)
  );
}

function hasHandbookState(state?: MWDocumentState | null): boolean {
  return Boolean(
    state?.handbook_title ||
    state?.handbook_sections?.length ||
    state?.handbook_source_type === 'upload' ||
    state?.handbook_uploaded_filename ||
    state?.handbook_red_flags?.length ||
    state?.handbook_blocking_error
  );
}

function hasPolicyState(state?: MWDocumentState | null): boolean {
  return Boolean(
    state?.policy_title ||
    state?.policy_type ||
    state?.policy_status ||
    state?.policy_additional_context ||
    state?.policy_content ||
    state?.policy_id ||
    (state?.policy_location_names && state.policy_location_names.length > 0) ||
    (state?.policy_locations && state.policy_locations.length > 0)
  );
}

function hasAnyPreviewState(state?: MWDocumentState | null, pdfUrl?: string | null): boolean {
  return Boolean(
    pdfUrl ||
    hasWorkbookState(state) ||
    hasReviewState(state) ||
    hasOnboardingState(state) ||
    hasPresentationState(state) ||
    hasHandbookState(state) ||
    hasPolicyState(state)
  );
}

function getThreadTypeLabel(taskType: MWThreadDetail['task_type'], isUnscopedChat: boolean): string {
  if (isUnscopedChat || taskType === 'chat') return 'chat';
  if (taskType === 'review') return 'review';
  if (taskType === 'workbook') return 'workbook';
  if (taskType === 'onboarding') return 'onboarding';
  if (taskType === 'presentation') return 'presentation';
  if (taskType === 'handbook') return 'handbook';
  if (taskType === 'policy') return 'policy';
  return 'offer letter';
}

function getPreviewTabLabel(previewKind: PreviewKind): string {
  if (previewKind === 'offer_letter') return 'Preview';
  if (previewKind === 'presentation') return 'Presentation';
  if (previewKind === 'workbook') return 'Workbook';
  if (previewKind === 'handbook') return 'Handbook';
  if (previewKind === 'policy') return 'Policy';
  if (previewKind === 'onboarding') return 'Onboarding';
  if (previewKind === 'review') return 'Review';
  return 'Summary';
}

function WorkbookPreview({ state, threadId, selectedSlideIndex, onSelectSlide }: {
  state: MWDocumentState;
  threadId?: string;
  selectedSlideIndex?: number | null;
  onSelectSlide?: (idx: number | null) => void;
}) {
  const [activeView, setActiveView] = useState<'workbook' | 'presentation'>('workbook');
  const sections = state.sections || [];
  const presentation = state.presentation;

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-2">
          <div className="inline-flex items-center border border-white/10">
            <button
              onClick={() => setActiveView('workbook')}
              className={`px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors ${
                activeView === 'workbook'
                  ? 'bg-white/10 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Workbook
            </button>
            <button
              onClick={() => setActiveView('presentation')}
              className={`px-2.5 py-1 text-[11px] uppercase tracking-wider transition-colors border-l border-white/10 ${
                activeView === 'presentation'
                  ? 'bg-white/10 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Presentation
            </button>
          </div>
          {activeView === 'presentation' && presentation && threadId && (
            <button
              onClick={() => matchaWork.downloadPresentationPdf(threadId, presentation.title || 'presentation')}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] border border-white/10 text-zinc-300 hover:text-zinc-100 hover:border-white/20 uppercase tracking-wider transition-colors"
            >
              Download PDF
            </button>
          )}
        </div>

        {activeView === 'workbook' ? (
          <>
        <div className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm p-6 transition-colors">
          <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 light:text-zinc-500 mb-1">HR Workbook</p>
          <h2 className="text-xl font-bold text-white light:text-zinc-900 tracking-tight transition-colors">
            {state.workbook_title || 'Untitled Workbook'}
          </h2>
          {state.company_name && (
            <p className="text-sm text-zinc-400 light:text-zinc-600 mt-1 transition-colors">{state.company_name}</p>
          )}
          {(state.industry || state.objective) && (
            <div className="flex flex-wrap gap-2 mt-4">
              {state.industry && (
                <span className="px-2 py-0.5 border border-white/10 bg-zinc-800 text-zinc-300 light:bg-zinc-100 light:border-zinc-200 light:text-zinc-700 text-[10px] uppercase tracking-wider transition-colors">
                  {state.industry}
                </span>
              )}
              {state.objective && (
                <span className="px-2 py-0.5 border border-matcha-500/20 bg-matcha-500/10 text-matcha-400 text-[10px] uppercase tracking-wider">
                  {state.objective}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {sections.length === 0 ? (
            <div className="border border-white/10 light:border-black/5 border-dashed p-12 text-center transition-colors">
              <div className="w-12 h-12 bg-zinc-800 border border-white/10 light:bg-black/[0.12] light:border-zinc-200 flex items-center justify-center mx-auto mb-4 text-zinc-600 light:text-zinc-400 transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-zinc-500 light:text-zinc-500 text-sm italic font-mono transition-colors">
                Waiting for sections to be generated...
              </p>
            </div>
          ) : (
            sections.map((section, idx) => (
              <div key={idx} className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm overflow-hidden transition-colors">
                <div className="px-5 py-3 border-b border-white/10 bg-zinc-900/30 light:border-black/5 light:bg-zinc-100/50 transition-colors">
                  <h3 className="text-sm font-bold text-zinc-200 light:text-zinc-800 tracking-wide uppercase transition-colors">
                    {section.title}
                  </h3>
                </div>
                <div className="px-5 py-4 prose prose-invert light:prose-zinc prose-sm max-w-none text-zinc-300 light:text-zinc-700 leading-relaxed font-sans transition-colors">
                  <ReactMarkdown>{section.content}</ReactMarkdown>
                </div>
              </div>
            ))
          )}
        </div>
          </>
        ) : (
          <div className="space-y-4">
            {!presentation || !Array.isArray(presentation.slides) || presentation.slides.length === 0 ? (
              <div className="border border-white/10 border-dashed p-12 text-center">
                <div className="w-12 h-12 bg-zinc-800 border border-white/10 flex items-center justify-center mx-auto mb-4 text-zinc-600">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h8M8 14h5m7 7H4a1 1 0 01-1-1V4a1 1 0 011-1h10.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V20a1 1 0 01-1 1z" />
                  </svg>
                </div>
                <p className="text-zinc-500 text-sm italic font-mono">
                  No presentation generated yet. Use Generate Presentation.
                </p>
              </div>
            ) : (
              <>
                <div className="bg-zinc-950 border border-white/10 overflow-hidden">
                  {presentation.cover_image_url && (
                    <img src={presentation.cover_image_url} alt="Cover" className="w-full h-48 object-cover" />
                  )}
                  <div className="p-5">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 mb-1">Presentation Deck</p>
                  <h2 className="text-xl font-bold text-white tracking-tight">{presentation.title}</h2>
                  {presentation.subtitle && (
                    <p className="text-sm text-zinc-400 mt-1">{presentation.subtitle}</p>
                  )}
                  <p className="text-xs text-zinc-500 mt-3">
                    {presentation.slide_count} slide{presentation.slide_count === 1 ? '' : 's'} · Generated {new Date(presentation.generated_at).toLocaleString()}
                  </p>
                  </div>
                </div>
                {presentation.slides.map((slide, idx) => {
                  const isSelected = selectedSlideIndex === idx;
                  return (
                    <div
                      key={`${slide.title}-${idx}`}
                      onClick={() => onSelectSlide?.(isSelected ? null : idx)}
                      className={`bg-zinc-950 border overflow-hidden transition-colors ${
                        onSelectSlide ? 'cursor-pointer' : ''
                      } ${
                        isSelected
                          ? 'border-matcha-500/60 ring-1 ring-matcha-500/20'
                          : 'border-white/10 hover:border-white/20'
                      }`}
                    >
                      <div className={`px-5 py-3 border-b flex items-center justify-between ${
                        isSelected ? 'border-matcha-500/30 bg-matcha-900/20' : 'border-white/10 bg-zinc-900/30'
                      }`}>
                        <h3 className="text-sm font-bold text-zinc-200 tracking-wide uppercase">{slide.title}</h3>
                        <div className="flex items-center gap-2">
                          {isSelected && (
                            <span className="text-[10px] text-matcha-400 font-mono uppercase tracking-wider">selected</span>
                          )}
                          <span className="text-[10px] text-zinc-500">Slide {idx + 1}</span>
                        </div>
                      </div>
                      <div className="px-5 py-4">
                        <ul className="space-y-1.5">
                          {(slide.bullets || []).map((bullet, bulletIdx) => (
                            <li key={`${bullet}-${bulletIdx}`} className="text-sm text-zinc-300 leading-relaxed">
                              • {bullet}
                            </li>
                          ))}
                        </ul>
                        {slide.speaker_notes && (
                          <div className="mt-4 p-3 bg-zinc-900 border border-white/10">
                            <p className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">Speaker Notes</p>
                            <p className="text-xs text-zinc-400 whitespace-pre-wrap">{slide.speaker_notes}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PresentationPreview({ state, threadId, selectedSlideIndex, onSelectSlide }: {
  state: MWDocumentState;
  threadId?: string;
  selectedSlideIndex?: number | null;
  onSelectSlide?: (idx: number | null) => void;
}) {
  const slides = state.slides || [];
  const title = state.presentation_title || 'Presentation';
  const subtitle = state.subtitle;
  const coverImageUrl = state.cover_image_url;

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-4">
        {/* Cover */}
        <div className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm overflow-hidden transition-colors">
          {coverImageUrl && (
            <img src={coverImageUrl} alt="Cover" className="w-full h-48 object-cover" />
          )}
          <div className="p-6">
            <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 light:text-zinc-500 mb-1">Presentation</p>
            <h2 className="text-xl font-bold text-white light:text-zinc-900 tracking-tight transition-colors">{title}</h2>
            {subtitle && <p className="text-sm text-zinc-400 light:text-zinc-600 mt-1 transition-colors">{subtitle}</p>}
            <div className="flex items-center gap-3 mt-4">
              <span className="text-xs text-zinc-500 light:text-zinc-500">{slides.length} slide{slides.length !== 1 ? 's' : ''}</span>
              {threadId && slides.length > 0 && (
                <>
                  <button
                    onClick={() => matchaWork.viewPresentationPdf(threadId)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] border border-white/10 light:border-black/5 light:bg-black/5 text-zinc-300 hover:text-zinc-100 light:text-zinc-700 light:hover:text-zinc-900 uppercase tracking-wider transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    View PDF
                  </button>
                  <button
                    onClick={() => matchaWork.downloadPresentationPdf(threadId, title)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] border border-white/10 light:border-black/5 light:bg-black/5 text-zinc-300 hover:text-zinc-100 light:text-zinc-700 light:hover:text-zinc-900 uppercase tracking-wider transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download PDF
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Slides */}
        {slides.length === 0 ? (
          <div className="border border-white/10 light:border-black/5 border-dashed p-12 text-center transition-colors">
            <p className="text-zinc-500 light:text-zinc-500 text-sm italic font-mono">Generating slides...</p>
          </div>
        ) : (
          slides.map((slide, idx) => {
            const isSelected = selectedSlideIndex === idx;
            return (
              <div
                key={idx}
                onClick={() => onSelectSlide?.(isSelected ? null : idx)}
                className={`bg-zinc-950 light:bg-white/80 light:shadow-sm border overflow-hidden transition-colors ${
                  onSelectSlide ? 'cursor-pointer' : ''
                } ${
                  isSelected
                    ? 'border-matcha-500/60 ring-1 ring-matcha-500/20 light:border-matcha-400 light:ring-matcha-500/30'
                    : 'border-white/10 hover:border-white/20 light:border-black/5 light:hover:border-zinc-300'
                }`}
              >
                <div className={`px-5 py-3 border-b flex items-center justify-between transition-colors ${
                  isSelected ? 'border-matcha-500/30 bg-matcha-900/20 light:bg-matcha-50 light:border-matcha-200' : 'border-white/10 bg-zinc-900/30 light:border-black/5 light:bg-zinc-100/50'
                }`}>
                  <h3 className="text-sm font-bold text-zinc-200 light:text-zinc-800 tracking-wide uppercase transition-colors">{slide.title}</h3>
                  <div className="flex items-center gap-2">
                    {isSelected && (
                      <span className="text-[10px] text-matcha-400 light:text-black font-mono uppercase tracking-wider transition-colors">selected</span>
                    )}
                    <span className="text-[10px] text-zinc-500 light:text-zinc-500">Slide {idx + 1}</span>
                  </div>
                </div>
                <div className="px-5 py-4">
                  <ul className="space-y-1.5">
                    {(slide.bullets || []).map((bullet, bulletIdx) => (
                      <li key={bulletIdx} className="text-sm text-zinc-300 light:text-zinc-700 leading-relaxed transition-colors">• {bullet}</li>
                    ))}
                  </ul>
                  {slide.speaker_notes && (
                    <div className="mt-4 p-3 bg-zinc-900 border border-white/10 light:bg-zinc-100/50 light:border-zinc-200 transition-colors">
                      <p className="text-[10px] uppercase tracking-widest text-zinc-500 light:text-zinc-500 font-bold mb-1">Speaker Notes</p>
                      <p className="text-xs text-zinc-400 light:text-zinc-600 whitespace-pre-wrap transition-colors">{slide.speaker_notes}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function PolicyPreview({ state }: { state: MWDocumentState }) {
  const title = state.policy_title || 'Workplace Policy';
  const policyType = state.policy_type || '';
  const status = state.policy_status || 'collecting';
  const locationNames: string[] = state.policy_location_names || [];
  const content: string = state.policy_content || '';

  const statusColor =
    status === 'created' ? 'text-green-400 bg-green-400/10' :
    status === 'generating' ? 'text-orange-400 bg-orange-400/10' :
    status === 'ready' ? 'text-blue-400 bg-blue-400/10' :
    'text-zinc-400 bg-zinc-400/10';

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 light:text-zinc-900 tracking-tight">{title}</h2>
          <div className="flex items-center gap-2 mt-1.5">
            {policyType && (
              <span className="text-[11px] font-medium text-zinc-300 light:text-zinc-600 px-2 py-0.5 bg-zinc-800 light:bg-zinc-200/60">
                {policyType.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
              </span>
            )}
            <span className={`text-[11px] font-medium px-2 py-0.5 ${statusColor}`}>
              {status.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
            </span>
          </div>
        </div>

        {locationNames.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {locationNames.map((loc, i) => (
              <span key={i} className="text-[11px] text-zinc-400 px-2 py-0.5 bg-zinc-800/60 border border-white/5">
                {loc}
              </span>
            ))}
          </div>
        )}

        {status === 'generating' && (
          <div className="flex items-center gap-2 p-3 bg-orange-400/5 border border-orange-400/10">
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs text-orange-300">Generating policy draft...</span>
          </div>
        )}

        {content ? (
          <div className="bg-zinc-950 border border-white/10 light:bg-white/20 light:border-white/40 p-5">
            <pre className="text-sm text-zinc-300 light:text-zinc-800 whitespace-pre-wrap font-serif leading-relaxed">{content}</pre>
          </div>
        ) : status === 'collecting' ? (
          <div className="text-center py-8 text-xs text-zinc-600">
            Describe your policy needs and Matcha will draft it using your compliance data.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OnboardingPreview({ state }: { state: MWDocumentState }) {
  const employees = (state.employees || []) as NonNullable<MWDocumentState['employees']>;
  const batchStatus = state.batch_status || 'collecting';
  const hasDefaults = Boolean(state.default_start_date || state.default_employment_type || state.default_work_state);

  const createdCount = employees.filter(e => e.status === 'created' || e.status === 'done').length;
  const errorCount = employees.filter(e => e.status === 'error').length;

  const statusColor = (status?: string | null) => {
    switch (status) {
      case 'created': case 'done': return 'green';
      case 'provisioning': return 'blue';
      case 'error': return 'red';
      default: return 'zinc';
    }
  };

  const badgeClasses = (color: string) => {
    switch (color) {
      case 'green': return 'border-green-500/30 bg-green-500/10 text-green-400 light:text-green-700 light:bg-green-100 light:border-green-300';
      case 'blue': return 'border-blue-500/30 bg-blue-500/10 text-blue-400 light:text-blue-700 light:bg-blue-100 light:border-blue-300';
      case 'red': return 'border-red-500/30 bg-red-500/10 text-red-400 light:text-red-700 light:bg-red-100 light:border-red-300';
      case 'amber': return 'border-amber-500/30 bg-amber-500/10 text-amber-400 light:text-amber-700 light:bg-amber-100 light:border-amber-300';
      default: return 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400 light:text-zinc-600 light:bg-zinc-100 light:border-zinc-300';
    }
  };

  const batchColor = batchStatus === 'complete' ? 'green' : batchStatus === 'processing' ? 'blue' : batchStatus === 'ready' ? 'amber' : 'zinc';

  const getInitials = (emp: (typeof employees)[0]) => {
    const first = emp.first_name?.trim() || '';
    const last = emp.last_name?.trim() || '';
    if (first && last) return (first[0] + last[0]).toUpperCase();
    const full = (first || last || (emp as Record<string, unknown>).name as string || (emp as Record<string, unknown>).full_name as string || '?');
    return full.slice(0, 2).toUpperCase();
  };

  const getName = (emp: (typeof employees)[0]) => {
    const full = `${emp.first_name || ''} ${emp.last_name || ''}`.trim();
    return full || (emp as Record<string, unknown>).name as string || (emp as Record<string, unknown>).full_name as string || 'Unnamed';
  };

  const initialsColor = (color: string) => {
    switch (color) {
      case 'green': return 'bg-green-500/20 text-green-400 border-green-500/30 light:bg-green-100 light:text-green-700 light:border-green-300';
      case 'blue': return 'bg-blue-500/20 text-blue-400 border-blue-500/30 light:bg-blue-100 light:text-blue-700 light:border-blue-300';
      case 'red': return 'bg-red-500/20 text-red-400 border-red-500/30 light:bg-red-100 light:text-red-700 light:border-red-300';
      default: return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30 light:bg-zinc-100 light:text-zinc-600 light:border-zinc-300';
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-2xl mx-auto space-y-4">
        {/* Header */}
        <div className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm p-6 transition-colors">
          <div className="flex items-center justify-between mb-1">
            <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 light:text-zinc-500">Employee Onboarding</p>
            <span className={`text-[10px] px-2 py-0.5 border ${badgeClasses(batchColor)}`}>
              {batchStatus}
            </span>
          </div>
          {state.company_name && (
            <p className="text-sm text-zinc-400 light:text-zinc-600 transition-colors">{state.company_name}</p>
          )}
          {employees.length > 0 && (
            <p className="text-xs text-zinc-500 light:text-zinc-500 mt-3">
              {employees.length} employee{employees.length !== 1 ? 's' : ''}
              {createdCount > 0 && <> · {createdCount} created</>}
              {errorCount > 0 && <> · {errorCount} error{errorCount !== 1 ? 's' : ''}</>}
            </p>
          )}
        </div>

        {/* Defaults */}
        {hasDefaults && (
          <div className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm p-4 space-y-2 transition-colors">
            <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500 light:text-zinc-500 mb-2">Batch Defaults</p>
            {state.default_start_date && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-24">Start Date</span>
                <span className="text-xs text-zinc-300 light:text-zinc-700">{state.default_start_date}</span>
              </div>
            )}
            {state.default_employment_type && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-24">Type</span>
                <span className="text-xs text-zinc-300 light:text-zinc-700">{state.default_employment_type}</span>
              </div>
            )}
            {state.default_work_state && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-24">Work State</span>
                <span className="text-xs text-zinc-300 light:text-zinc-700">{state.default_work_state}</span>
              </div>
            )}
          </div>
        )}

        {/* Employee Cards */}
        {employees.length > 0 ? (
          <div className="space-y-3">
            {employees.map((emp, idx) => {
              const color = statusColor(emp.status);
              const name = getName(emp);
              const initials = getInitials(emp);
              const provEntries = emp.provisioning_results ? Object.entries(emp.provisioning_results) : [];

              return (
                <div key={emp.employee_id || idx} className="bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm p-4 transition-colors">
                  {/* Top row: avatar + name + status */}
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 flex items-center justify-center text-[11px] font-bold border ${initialsColor(color)}`}>
                      {initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-zinc-200 light:text-zinc-800 truncate">{name}</p>
                    </div>
                    {emp.status && (
                      <span className={`text-[10px] px-2 py-0.5 border flex-shrink-0 ${badgeClasses(color)}`}>
                        {emp.status}
                      </span>
                    )}
                  </div>

                  {/* Detail rows */}
                  <div className="mt-3 ml-11 space-y-1.5">
                    {emp.work_email && (
                      <p className="text-xs text-zinc-400 light:text-zinc-600 font-mono truncate">{emp.work_email}</p>
                    )}
                    {emp.personal_email && (
                      <p className="text-xs text-zinc-500 light:text-zinc-500 truncate">{emp.personal_email}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {emp.employment_type && (
                        <span className="text-[10px] px-1.5 py-0.5 border border-purple-500/30 bg-purple-500/10 text-purple-400 light:text-purple-700 light:bg-purple-100 light:border-purple-300">
                          {emp.employment_type}
                        </span>
                      )}
                      {emp.work_state && (
                        <span className="text-[10px] px-1.5 py-0.5 border border-blue-500/30 bg-blue-500/10 text-blue-400 light:text-blue-700 light:bg-blue-100 light:border-blue-300">
                          {emp.work_state}
                        </span>
                      )}
                    </div>
                    {emp.start_date && (
                      <div className="flex items-center gap-1.5 text-xs text-zinc-400 light:text-zinc-600">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        {emp.start_date}
                      </div>
                    )}
                  </div>

                  {/* Error banner */}
                  {emp.status === 'error' && emp.error && (
                    <div className="mt-3 ml-11 flex items-start gap-2 bg-red-500/10 border border-red-500/20 light:bg-red-50 light:border-red-200 p-2.5">
                      <svg className="w-3.5 h-3.5 text-red-400 light:text-red-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                      </svg>
                      <p className="text-xs text-red-300 light:text-red-700">{emp.error}</p>
                    </div>
                  )}

                  {/* Provisioning results */}
                  {provEntries.length > 0 && (
                    <div className="mt-3 ml-11 flex flex-wrap gap-2">
                      {provEntries.map(([service, result]) => {
                        const isSuccess = result === 'triggered' || result === 'success';
                        return (
                          <span
                            key={service}
                            className={`text-[10px] px-1.5 py-0.5 border ${isSuccess
                              ? 'border-green-500/30 bg-green-500/10 text-green-400 light:text-green-700 light:bg-green-100 light:border-green-300'
                              : 'border-red-500/30 bg-red-500/10 text-red-400 light:text-red-700 light:bg-red-100 light:border-red-300'
                            }`}
                          >
                            {service}: {result}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : batchStatus ? (
          <div className="border border-white/10 light:border-black/5 border-dashed p-12 text-center transition-colors">
            <div className="w-12 h-12 bg-zinc-800 border border-white/10 light:bg-black/[0.12] light:border-zinc-200 flex items-center justify-center mx-auto mb-4 text-zinc-600 light:text-zinc-400 transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <p className="text-zinc-500 light:text-zinc-500 text-sm italic font-mono transition-colors">
              Collecting employee details...
            </p>
          </div>
        ) : (
          <div className="border border-white/10 light:border-black/5 border-dashed p-12 text-center transition-colors">
            <div className="w-12 h-12 bg-zinc-800 border border-white/10 light:bg-black/[0.12] light:border-zinc-200 flex items-center justify-center mx-auto mb-4 text-zinc-600 light:text-zinc-400 transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <p className="text-zinc-500 light:text-zinc-500 text-sm italic font-mono transition-colors">
              Describe the employees you'd like to onboard...
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function parseEmailList(input: string): string[] {
  const matches = input.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [];
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const raw of matches) {
    const email = raw.trim().toLowerCase();
    if (!email || seen.has(email)) continue;
    seen.add(email);
    normalized.push(email);
  }
  return normalized;
}

function isInsufficientCreditsMessage(value: string): boolean {
  const text = value.toLowerCase();
  return text.includes('insufficient credits') || text.includes('out of credits');
}

function MessageBubble({ msg }: { msg: MWMessage }) {
  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-zinc-500 bg-zinc-800 light:bg-zinc-200/50 light:backdrop-blur-md light:text-zinc-600 border border-white/10 light:border-black/5 px-3 py-1 transition-colors">
          {msg.content}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 bg-matcha-600 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] flex items-center justify-center mr-2 flex-shrink-0 mt-0.5 rounded-sm transition-colors">
          <svg className="w-3.5 h-3.5 text-white light:text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
          </svg>
        </div>
      )}
      <div
        className={`max-w-[75%] px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap transition-colors ${
          isUser
            ? 'bg-matcha-600 text-white light:bg-black light:shadow-md'
            : 'bg-zinc-800 text-zinc-200 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:text-zinc-800 light:shadow-sm light:backdrop-blur-md'
        }`}
      >
        {msg.content}
        {msg.version_created && !isUser && (
          <div className="mt-1.5 text-xs opacity-50 light:text-zinc-500">
            Updated to v{msg.version_created}
          </div>
        )}
      </div>
    </div>
  );
}

// Simple thread cache — avoids re-fetching when switching between threads
type ThreadCacheEntry = {
  thread: MWThreadDetail;
  versions?: MWDocumentVersion[];
  pdfUrl: string | null;
  ts: number;
};

type AccountCacheEntry = {
  usage: MWUsageSummaryResponse | null;
  balance: number | null;
  ts: number;
};

const threadCachesByScope = new Map<string, Map<string, ThreadCacheEntry>>();
const THREAD_CACHE_TTL = 60_000; // 60 seconds

// Account-level cache (usage + billing) — shared across threads
const accountCacheByScope = new Map<string, AccountCacheEntry>();
const ACCOUNT_CACHE_TTL = 120_000; // 2 minutes

function getMatchaWorkCompanyId(profile: CurrentUserResponse['profile'] | null): string | null {
  if (profile && 'company_id' in profile && typeof profile.company_id === 'string') {
    return profile.company_id;
  }
  return null;
}

function getMatchaWorkCacheScope(userId: string | null | undefined, companyId: string | null): string | null {
  if (!userId) return null;
  return companyId ? `${userId}:${companyId}` : userId;
}

function getThreadCache(scope: string | null): Map<string, ThreadCacheEntry> | null {
  if (!scope) return null;
  let cache = threadCachesByScope.get(scope);
  if (!cache) {
    cache = new Map<string, ThreadCacheEntry>();
    threadCachesByScope.set(scope, cache);
  }
  return cache;
}

function setThreadCacheEntry(scope: string | null, threadId: string, entry: ThreadCacheEntry): void {
  const cache = getThreadCache(scope);
  if (!cache) return;
  cache.set(threadId, entry);
  if (cache.size > 10) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].ts - b[1].ts)[0];
    if (oldest) cache.delete(oldest[0]);
  }
}

function mergeThreadCacheEntry(scope: string | null, threadId: string, patch: Partial<ThreadCacheEntry>): void {
  const cache = getThreadCache(scope);
  if (!cache) return;
  const existing = cache.get(threadId);
  if (!existing) return;
  cache.set(threadId, { ...existing, ...patch, ts: Date.now() });
}

function invalidateThreadCacheEntry(scope: string | null, threadId: string): void {
  getThreadCache(scope)?.delete(threadId);
}

function getAccountCache(scope: string | null): AccountCacheEntry | null {
  if (!scope) return null;
  return accountCacheByScope.get(scope) || null;
}

function setAccountCacheEntry(scope: string | null, entry: AccountCacheEntry): void {
  if (!scope) return;
  accountCacheByScope.set(scope, entry);
}

function invalidateAccountCache(scope: string | null): void {
  if (!scope) return;
  accountCacheByScope.delete(scope);
}

export default function MatchaWorkThread() {
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();

  const [thread, setThread] = useState<MWThreadDetail | null>(null);
  const [messages, setMessages] = useState<MWMessage[]>([]);
  const [versions, setVersions] = useState<MWDocumentVersion[]>([]);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('chat');
  const [previewPanelOpen, setPreviewPanelOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [creatingChat, setCreatingChat] = useState(false);
  const [showFinalizeConfirm, setShowFinalizeConfirm] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<(MWTokenUsage & { stage: 'estimate' | 'final' }) | null>(null);
  const [usageSummary, setUsageSummary] = useState<MWUsageSummaryResponse | null>(null);
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [showReviewRequestsModal, setShowReviewRequestsModal] = useState(false);
  const [selectedSlideIndex, setSelectedSlideIndex] = useState<number | null>(null);
  const [generatingPresentation, setGeneratingPresentation] = useState(false);
  const [sendingReviewRequests, setSendingReviewRequests] = useState(false);
  const [reviewRecipientInput, setReviewRecipientInput] = useState('');
  const [reviewEmailMessage, setReviewEmailMessage] = useState('');
  const [loadingActiveHandbooks, setLoadingActiveHandbooks] = useState(false);
  const [sendingHandbookSignatures, setSendingHandbookSignatures] = useState(false);
  const [showHandbookSelectorModal, setShowHandbookSelectorModal] = useState(false);
  const [showHandbookDistributeModal, setShowHandbookDistributeModal] = useState(false);
  const [activeHandbooks, setActiveHandbooks] = useState<HandbookListItem[]>([]);
  const [selectedHandbook, setSelectedHandbook] = useState<{ id: string; title: string } | null>(null);

  const { user, profile } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [matchaWorkModelMode, setMatchaWorkModelMode] = useState<'light' | 'heavy'>('light');
  const cacheScope = getMatchaWorkCacheScope(user?.id, getMatchaWorkCompanyId(profile));

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const loadVersions = useCallback(async (force = false) => {
    if (!threadId || loadingVersions) return;

    const cached = getThreadCache(cacheScope)?.get(threadId);
    if (!force && cached?.versions) {
      setVersions(cached.versions);
      setVersionsLoaded(true);
      return;
    }

    try {
      setLoadingVersions(true);
      const verData = await matchaWork.getVersions(threadId);
      setVersions(verData);
      setVersionsLoaded(true);
      mergeThreadCacheEntry(cacheScope, threadId, { versions: verData });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load versions');
    } finally {
      setLoadingVersions(false);
    }
  }, [cacheScope, loadingVersions, threadId]);

  const loadThread = useCallback(async () => {
    if (!threadId) return;
    try {
      setTokenUsage(null);
      setError(null);
      setVersions([]);
      setVersionsLoaded(false);
      setPdfUrl(null);
      const scopedThreadCache = getThreadCache(cacheScope);

      // Serve from cache instantly if available
      const cached = scopedThreadCache?.get(threadId);
      if (cached && Date.now() - cached.ts < THREAD_CACHE_TTL) {
        setThread(cached.thread);
        setMessages(cached.thread.messages);
        setVersions(cached.versions || []);
        setVersionsLoaded(Boolean(cached.versions));
        setPdfUrl(cached.pdfUrl);
        setLoading(false);
        // Open preview panel if cached thread has content
        const cst = cached.thread.current_state || {};
        if (hasAnyPreviewState(cst, cached.pdfUrl)) {
          setPreviewPanelOpen(true);
        }
      } else {
        setLoading(true);
      }

      // Load account-level data from cache or fetch
      const cachedAccount = getAccountCache(cacheScope);
      if (cachedAccount && Date.now() - cachedAccount.ts < ACCOUNT_CACHE_TTL) {
        setUsageSummary(cachedAccount.usage);
        setCreditBalance(cachedAccount.balance);
      } else {
        // Fire these in background — don't block thread rendering
        Promise.all([
          matchaWork.getUsageSummary(30).catch(() => null),
          matchaWork.getBillingBalance().catch(() => null),
        ]).then(([usageData, billingData]) => {
          const balance = typeof billingData?.credits_remaining === 'number' ? billingData.credits_remaining : null;
          setUsageSummary(usageData);
          setCreditBalance(balance);
          setAccountCacheEntry(cacheScope, { usage: usageData, balance, ts: Date.now() });
        });
      }

      // Fetch thread first so the main UI can render before optional secondary data.
      const threadData = await matchaWork.getThread(threadId);
      const canReuseCachedVersions = Boolean(cached?.versions && cached.thread.version === threadData.version);
      const canReuseCachedPdf = Boolean(cached?.pdfUrl && cached.thread.version === threadData.version);
      const pdfUrlResult: string | null = canReuseCachedPdf ? cached?.pdfUrl || null : null;

      setThread(threadData);
      setMessages(threadData.messages);
      setVersions(canReuseCachedVersions ? cached?.versions || [] : []);
      setVersionsLoaded(canReuseCachedVersions);
      setPdfUrl(pdfUrlResult);

      // Auto-open preview panel if thread already has content
      const st = threadData.current_state || {};
      const threadHasContent = hasAnyPreviewState(
        st,
        pdfUrlResult || (threadData.task_type === 'offer_letter' && threadData.version > 0 ? '__pending__' : null)
      );
      if (threadHasContent) {
        setPreviewPanelOpen(true);
      }

      // Update cache
      setThreadCacheEntry(cacheScope, threadId, {
        thread: threadData,
        versions: canReuseCachedVersions ? cached?.versions : undefined,
        pdfUrl: pdfUrlResult,
        ts: Date.now(),
      });

      if (threadData.task_type === 'offer_letter' && threadData.version > 0 && !canReuseCachedPdf) {
        void matchaWork.getPdf(threadId)
          .then((pdfData) => {
            setPdfUrl(pdfData.pdf_url);
            mergeThreadCacheEntry(cacheScope, threadId, { pdfUrl: pdfData.pdf_url });
          })
          .catch(() => {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load thread');
    } finally {
      setLoading(false);
    }
  }, [cacheScope, threadId]);

  useEffect(() => {
    loadThread();
  }, [loadThread]);

  useEffect(() => {
    if (!isAdmin) return;
    adminPlatformSettings.get().then(s => {
      setMatchaWorkModelMode(s.matcha_work_model_mode as 'light' | 'heavy');
    }).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!showVersions || versionsLoaded || loadingVersions) return;
    void loadVersions();
  }, [loadVersions, loadingVersions, showVersions, versionsLoaded]);

  // Load PDF as blob URL to avoid cross-origin iframe restrictions
  useEffect(() => {
    if (!pdfUrl || !previewPanelOpen) {
      setPdfBlobUrl(null);
      return;
    }
    let revoked = false;
    let blobUrl: string | null = null;
    const token = getAccessToken();
    fetch(`/api/matcha-work/threads/${threadId}/pdf/proxy`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => {
        if (!r.ok) throw new Error(`PDF proxy returned ${r.status}`);
        return r.blob();
      })
      .then(blob => {
        if (revoked) return;
        blobUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(blobUrl);
      })
      .catch(() => {
        // fall back to direct URL if proxy fails
        if (!revoked) setPdfBlobUrl(pdfUrl);
      });
    return () => {
      revoked = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [pdfUrl, previewPanelOpen, threadId]);

  const handleToggleModel = async () => {
    const next = matchaWorkModelMode === 'light' ? 'heavy' : 'light';
    setMatchaWorkModelMode(next);
    try {
      await adminPlatformSettings.updateMatchaWorkModelMode(next);
    } catch {
      setMatchaWorkModelMode(matchaWorkModelMode);
    }
  };

  const handleSend = async (overrideContent?: string) => {
    const content = (overrideContent || input).trim();
    if (!content || !threadId || sending || isOutOfCredits) return;
    const capturedSlideIndex = selectedSlideIndex;
    setInput('');
    setSelectedSlideIndex(null);
    setSending(true);
    setError(null);
    setTokenUsage(null);

    let streamError: string | null = null;
    let receivedComplete = false;
    let shouldRefreshVersions = false;

    try {
      await matchaWork.sendMessageStream(threadId, content, (event) => {
        if (event.type === 'usage') {
          setTokenUsage(event.data);
          return;
        }

        if (event.type === 'complete') {
          const resp = event.data;
          receivedComplete = true;
          invalidateThreadCacheEntry(cacheScope, threadId);
          invalidateAccountCache(cacheScope);
          setMessages((prev) => [...prev, resp.user_message, resp.assistant_message]);
          setThread((prev) =>
            prev
              ? { ...prev, current_state: resp.current_state, version: resp.version, ...(resp.task_type ? { task_type: resp.task_type } : {}) }
              : prev
          );
          if (resp.version > 0) {
            shouldRefreshVersions = true;
          }
          const hasWorkbookStateResp = hasWorkbookState(resp.current_state);
          const hasReviewStateResp = hasReviewState(resp.current_state);
          const hasOnboardingStateResp = hasOnboardingState(resp.current_state);
          const hasPresentationStateResp = hasPresentationState(resp.current_state);
          const hasHandbookStateResp = hasHandbookState(resp.current_state);
          const hasPolicyStateResp = hasPolicyState(resp.current_state);
          if (resp.pdf_url) {
            setPdfUrl(resp.pdf_url);
            setPreviewPanelOpen(true);
            setActiveTab('preview');
          } else if (hasWorkbookStateResp || hasReviewStateResp || hasOnboardingStateResp || hasPresentationStateResp || hasHandbookStateResp || hasPolicyStateResp) {
            setPreviewPanelOpen(true);
            setActiveTab('preview');
          }
          if (resp.token_usage) {
            setTokenUsage({ ...resp.token_usage, stage: 'final' });
            setUsageSummary((prev) => {
              if (!prev || !resp.token_usage?.model) return prev;

              const promptTokens = resp.token_usage.prompt_tokens ?? 0;
              const completionTokens = resp.token_usage.completion_tokens ?? 0;
              const totalTokens =
                resp.token_usage.total_tokens ?? promptTokens + completionTokens;
              const costDollars = resp.token_usage.cost_dollars ?? 0;
              const model = resp.token_usage.model;
              const nowIso = new Date().toISOString();

              let found = false;
              const byModel = prev.by_model.map((row) => {
                if (row.model !== model) return row;
                found = true;
                return {
                  ...row,
                  prompt_tokens: row.prompt_tokens + promptTokens,
                  completion_tokens: row.completion_tokens + completionTokens,
                  total_tokens: row.total_tokens + totalTokens,
                  total_cost_dollars: row.total_cost_dollars + costDollars,
                  operation_count: row.operation_count + 1,
                  estimated_operations: row.estimated_operations + (resp.token_usage?.estimated ? 1 : 0),
                  last_seen_at: nowIso,
                };
              });

              if (!found) {
                byModel.push({
                  model,
                  prompt_tokens: promptTokens,
                  completion_tokens: completionTokens,
                  total_tokens: totalTokens,
                  total_cost_dollars: costDollars,
                  operation_count: 1,
                  estimated_operations: resp.token_usage?.estimated ? 1 : 0,
                  first_seen_at: nowIso,
                  last_seen_at: nowIso,
                });
              }

              byModel.sort((a, b) => b.total_tokens - a.total_tokens);

              return {
                ...prev,
                totals: {
                  prompt_tokens: prev.totals.prompt_tokens + promptTokens,
                  completion_tokens: prev.totals.completion_tokens + completionTokens,
                  total_tokens: prev.totals.total_tokens + totalTokens,
                  total_cost_dollars: prev.totals.total_cost_dollars + costDollars,
                  operation_count: prev.totals.operation_count + 1,
                  estimated_operations: prev.totals.estimated_operations + (resp.token_usage?.estimated ? 1 : 0),
                },
                by_model: byModel,
              };
            });
          }
          void matchaWork
            .getBillingBalance()
            .then((data) => setCreditBalance(data.credits_remaining))
            .catch(() => {});
          return;
        }

        if (event.type === 'error') {
          const message = event.message || 'Failed to send message';
          if (isInsufficientCreditsMessage(message)) {
            setCreditBalance(0);
            streamError = 'Out of credits. Purchase more credits to continue using Matcha Work.';
          } else {
            streamError = message;
          }
        }
      }, undefined, capturedSlideIndex ?? undefined);

      if (streamError) {
        setError(streamError);
      } else if (!receivedComplete) {
        setError('Failed to send message');
      }

      if (shouldRefreshVersions && versionsLoaded) {
        void loadVersions(true);
      }
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 402) {
        setCreditBalance(0);
        setError('Out of credits. Purchase more credits to continue using Matcha Work.');
      } else {
        const message = err instanceof Error ? err.message : 'Failed to send message';
        if (isInsufficientCreditsMessage(message)) {
          setCreditBalance(0);
          setError('Out of credits. Purchase more credits to continue using Matcha Work.');
        } else {
          setError(message);
        }
      }
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleLogoUpload = async (file: File) => {
    if (!threadId) return;
    try {
      setError(null);
      const resp = await matchaWork.uploadLogo(threadId, file);
      invalidateThreadCacheEntry(cacheScope, threadId);
      // Update thread state immediately
      setThread((prev) =>
        prev
          ? {
              ...prev,
              current_state: { ...prev.current_state, company_logo_url: resp.logo_url },
            }
          : prev
      );
      // Refresh PDF if in offer letter mode
      if (isOfferLetter) {
        const pdfData = await matchaWork.getPdf(threadId);
        setPdfUrl(pdfData.pdf_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload logo');
    }
  };

  const handleHandbookUpload = async (file: File) => {
    if (!threadId || isArchived || isFinalized) return;
    try {
      setError(null);
      const resp = await matchaWork.uploadHandbook(threadId, file);
      invalidateThreadCacheEntry(cacheScope, threadId);
      invalidateAccountCache(cacheScope);
      setThread(resp);
      setMessages(resp.messages);
      setPreviewPanelOpen(true);
      setActiveTab('preview');
      setVersionsLoaded(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload handbook');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleRevert = async (version: number) => {
    if (!threadId) return;
    try {
      setSending(true);
      const resp = await matchaWork.revert(threadId, version);
      invalidateThreadCacheEntry(cacheScope, threadId);
      setMessages((prev) => [...prev, resp.user_message, resp.assistant_message]);
      if (thread) {
        setThread((prev) => prev ? { ...prev, current_state: resp.current_state, version: resp.version, ...(resp.task_type ? { task_type: resp.task_type } : {}) } : prev);
      }
      if (resp.pdf_url) setPdfUrl(resp.pdf_url);
      if (versionsLoaded) {
        void loadVersions(true);
      } else {
        setVersionsLoaded(false);
      }
      setShowVersions(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revert');
    } finally {
      setSending(false);
    }
  };

  const handleFinalize = async () => {
    if (!threadId) return;
    try {
      setFinalizing(true);
      const resp = await matchaWork.finalize(threadId);
      invalidateThreadCacheEntry(cacheScope, threadId);
      setThread((prev) => prev ? { ...prev, status: 'finalized' } : prev);
      if (resp.pdf_url) setPdfUrl(resp.pdf_url);
      setShowFinalizeConfirm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to finalize');
    } finally {
      setFinalizing(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!threadId || savingDraft || isArchived || !isOfferLetter) return;
    try {
      setSavingDraft(true);
      setError(null);
      const resp = await matchaWork.saveDraft(threadId);
      invalidateThreadCacheEntry(cacheScope, threadId);
      setThread((prev) =>
        prev ? { ...prev, linked_offer_letter_id: resp.linked_offer_letter_id } : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleCreateChat = async () => {
    if (creatingChat || !thread) return;
    try {
      setCreatingChat(true);
      setError(null);
      const created = await matchaWork.createThread({ title: 'Untitled Chat' });
      navigate(`/app/matcha/work/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create chat');
    } finally {
      setCreatingChat(false);
    }
  };

  const handleOpenReviewRequestsModal = () => {
    if (!thread) return;
    const existing = (thread.current_state.recipient_emails || []).join(', ');
    setReviewRecipientInput(existing);
    setReviewEmailMessage('');
    setShowReviewRequestsModal(true);
  };

  const handleSendReviewRequests = async () => {
    if (!threadId || sendingReviewRequests) return;

    const recipientEmails = parseEmailList(reviewRecipientInput);
    if (recipientEmails.length === 0) {
      setError('Add at least one valid recipient email');
      return;
    }

    try {
      setSendingReviewRequests(true);
      setError(null);
      await matchaWork.sendReviewRequests(threadId, {
        recipient_emails: recipientEmails,
        custom_message: reviewEmailMessage.trim() || undefined,
      });
      setShowReviewRequestsModal(false);
      invalidateThreadCacheEntry(cacheScope, threadId);
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send review requests');
    } finally {
      setSendingReviewRequests(false);
    }
  };

  const handleOpenHandbookSignatures = async () => {
    if (!threadId || loadingActiveHandbooks || isArchived || !isWorkbook) return;
    try {
      setLoadingActiveHandbooks(true);
      setError(null);
      const allHandbooks = await handbooks.list();
      const active = allHandbooks.filter((row) => row.status === 'active');
      setActiveHandbooks(active);

      if (active.length === 0) {
        setError('No active handbooks found. Publish a handbook first in /handbook.');
        return;
      }

      if (active.length === 1) {
        setSelectedHandbook({ id: active[0].id, title: active[0].title });
        setShowHandbookDistributeModal(true);
        return;
      }

      setShowHandbookSelectorModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load active handbooks');
    } finally {
      setLoadingActiveHandbooks(false);
    }
  };

  const handleGeneratePresentation = async () => {
    if (!threadId || generatingPresentation || isArchived || !isWorkbook || isFinalized) return;
    try {
      setGeneratingPresentation(true);
      setError(null);
      await matchaWork.generatePresentation(threadId);
      invalidateThreadCacheEntry(cacheScope, threadId);
      await loadThread();
      setActiveTab('preview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate presentation');
    } finally {
      setGeneratingPresentation(false);
    }
  };

  const handleSelectHandbookForSignatures = (handbook: HandbookListItem) => {
    setSelectedHandbook({ id: handbook.id, title: handbook.title });
    setShowHandbookSelectorModal(false);
    setShowHandbookDistributeModal(true);
  };

  const handleSendHandbookSignatures = async (employeeIds?: string[]) => {
    if (!threadId || !selectedHandbook || sendingHandbookSignatures) return;
    try {
      setSendingHandbookSignatures(true);
      setError(null);
      const result = await matchaWork.sendHandbookSignatures(threadId, {
        handbook_id: selectedHandbook.id,
        employee_ids: employeeIds,
      });
      alert(
        `Distributed handbook v${result.handbook_version} to ${result.assigned_count} employees (${result.skipped_existing_count} already assigned).`
      );
      setShowHandbookDistributeModal(false);
      invalidateThreadCacheEntry(cacheScope, threadId);
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send handbook signatures');
    } finally {
      setSendingHandbookSignatures(false);
    }
  };

  const isFinalized = thread?.status === 'finalized';
  const isArchived = thread?.status === 'archived';
  const isOfferLetter = thread?.task_type === 'offer_letter';
  const isReview = thread?.task_type === 'review';
  const isWorkbook = thread?.task_type === 'workbook';
  const isOnboarding = thread?.task_type === 'onboarding';
  const isPresentation = thread?.task_type === 'presentation';
  const isHandbook = thread?.task_type === 'handbook';
  const isPolicy = thread?.task_type === 'policy';
  const isUploadHandbook = isHandbook && thread?.current_state.handbook_source_type === 'upload';
  const reviewStatuses: MWReviewRequestStatus[] = (thread?.current_state.review_request_statuses || [])
    .filter((row): row is MWReviewRequestStatus => Boolean(row && typeof row === 'object' && row.email));
  const reviewStrengths = toItemList(thread?.current_state.strengths);
  const reviewGrowthAreas = toItemList(thread?.current_state.growth_areas);
  const reviewExpectedResponses = thread?.current_state.review_expected_responses ?? reviewStatuses.length;
  const reviewReceivedResponses = thread?.current_state.review_received_responses ?? reviewStatuses.filter((row) => row.status === 'submitted').length;
  const reviewPendingResponses = thread?.current_state.review_pending_responses ?? Math.max(reviewExpectedResponses - reviewReceivedResponses, 0);
  const isUnscopedChat = thread
    ? thread.version === 0 &&
      messages.length === 0 &&
      Object.keys(thread.current_state || {}).length === 0
    : false;
  const hasOfferLetterPreviewContent = Boolean(pdfUrl || (isOfferLetter && thread?.version && thread.version > 0));
  const hasPresentationPreviewContent = Boolean(
    hasPresentationState(thread?.current_state)
  );
  const hasWorkbookPreviewContent = !isPresentation && !hasPresentationPreviewContent && hasWorkbookState(thread?.current_state);
  const hasReviewPreviewContent = hasReviewState(thread?.current_state);
  const hasOnboardingPreviewContent = hasOnboardingState(thread?.current_state);
  const hasHandbookPreviewContent = hasHandbookState(thread?.current_state);
  const hasPolicyPreviewContent = hasPolicyState(thread?.current_state);
  const hasPreviewContent = !isUnscopedChat && (
    hasOfferLetterPreviewContent ||
    hasWorkbookPreviewContent ||
    hasReviewPreviewContent ||
    hasOnboardingPreviewContent ||
    hasHandbookPreviewContent ||
    hasPresentationPreviewContent ||
    hasPolicyPreviewContent
  );
  const previewKind: PreviewKind =
    isOfferLetter ? 'offer_letter'
    : isPresentation ? 'presentation'
    : isWorkbook ? 'workbook'
    : isHandbook ? 'handbook'
    : isPolicy ? 'policy'
    : isOnboarding ? 'onboarding'
    : hasOfferLetterPreviewContent ? 'offer_letter'
    : hasPresentationPreviewContent ? 'presentation'
    : hasWorkbookPreviewContent ? 'workbook'
    : hasHandbookPreviewContent ? 'handbook'
    : hasPolicyPreviewContent ? 'policy'
    : hasOnboardingPreviewContent ? 'onboarding'
    : hasReviewPreviewContent ? 'review'
    : null;
  const isOutOfCredits = creditBalance !== null && creditBalance <= 0;
  const isLowCredits = creditBalance !== null && creditBalance > 0 && creditBalance < 2.0;
  const inputDisabled = isFinalized || isArchived || sending || isOutOfCredits;
  const formatTokenCount = (value: number | null | undefined) =>
    value == null ? '—' : value.toLocaleString();

  useEffect(() => {
    if (!(previewPanelOpen && hasPreviewContent) && activeTab === 'preview') {
      setActiveTab('chat');
    }
  }, [activeTab, hasPreviewContent, previewPanelOpen]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center">
          <p className="text-zinc-400">Thread not found</p>
          <button
            onClick={() => navigate('/app/matcha/work/chats')}
            className="mt-3 text-sm text-matcha-400 hover:text-matcha-300"
          >
            Open Chats
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full relative" style={{ height: 'calc(100vh - 56px)' }}>
      <div className="fixed inset-0 pointer-events-none -z-10 transition-colors duration-500 light:bg-black/[0.12]" />
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 light:border-white/30 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] flex-shrink-0 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/app/matcha/work/chats')}
            className="text-zinc-500 hover:text-zinc-200 light:text-zinc-500 light:hover:text-zinc-800 transition-colors flex-shrink-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-medium text-zinc-200 light:text-zinc-900 truncate transition-colors">{thread.title}</h1>
              <span className="text-[10px] text-zinc-600 light:text-zinc-500 font-mono border border-white/10 light:border-zinc-200 px-1.5 py-0.5 uppercase tracking-wider shrink-0 transition-colors">
                v{thread.version}
              </span>
              <span className="hidden sm:inline text-[10px] text-zinc-500 border border-white/10 px-1.5 py-0.5 uppercase tracking-wider shrink-0">
                {getThreadTypeLabel(thread.task_type, isUnscopedChat)}
              </span>
              {isFinalized && <span className="text-[10px] text-blue-400 border border-blue-500/20 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Finalized</span>}
              {isArchived && <span className="text-[10px] text-zinc-500 border border-white/10 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Archived</span>}
              {thread.linked_offer_letter_id && <span className="text-[10px] text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 uppercase tracking-wider shrink-0">Draft Saved</span>}
              {tokenUsage ? (
                <span className="hidden sm:inline text-[10px] text-zinc-300 font-mono border border-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 shrink-0">
                  {tokenUsage.estimated ? '~' : ''}{formatTokenCount(tokenUsage.total_tokens)} tok{tokenUsage.cost_dollars != null ? ` · $${tokenUsage.cost_dollars.toFixed(4)}` : ''}
                </span>
              ) : usageSummary && usageSummary.totals.total_tokens > 0 ? (
                <span className="hidden sm:inline text-[10px] text-zinc-300 font-mono border border-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 shrink-0">
                  {formatTokenCount(usageSummary.totals.total_tokens)} tok · ${usageSummary.totals.total_cost_dollars.toFixed(4)}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isAdmin && (
            <button
              onClick={handleToggleModel}
              className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono border transition-colors ${
                matchaWorkModelMode === 'heavy'
                  ? 'text-amber-400 border-amber-500/20 hover:border-amber-500/40'
                  : 'text-zinc-500 border-white/10 hover:border-white/20'
              }`}
              title={matchaWorkModelMode === 'heavy' ? 'Switch to light (flash)' : 'Switch to heavy (3.1 pro)'}
            >
              {matchaWorkModelMode === 'heavy' ? '3.1 pro' : 'flash'}
            </button>
          )}

          {/* Preview panel toggle */}
          {hasPreviewContent && (
            <button
              onClick={() => { setPreviewPanelOpen((v) => !v); if (!previewPanelOpen) setActiveTab('preview'); }}
              className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono border transition-colors ${
                previewPanelOpen
                  ? 'text-matcha-400 border-matcha-500/20 hover:border-matcha-500/40'
                  : 'text-zinc-500 border-white/10 hover:border-white/20'
              }`}
              title={previewPanelOpen ? 'Hide preview panel' : 'Show preview panel'}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7" />
              </svg>
              {previewPanelOpen ? 'Hide' : 'Assets'}
            </button>
          )}

          {/* Mobile preview toggle */}
          {previewPanelOpen && hasPreviewContent && (
            <div className="flex md:hidden border border-white/10">
              <button
                onClick={() => setActiveTab('chat')}
                className={`px-3 py-1 text-xs uppercase tracking-wider transition-colors ${activeTab === 'chat' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
              >Chat</button>
              <button
                onClick={() => setActiveTab('preview')}
                className={`px-3 py-1 text-xs uppercase tracking-wider transition-colors border-l border-white/10 ${activeTab === 'preview' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
              >{getPreviewTabLabel(previewKind)}</button>
            </div>
          )}

          <button
            onClick={handleCreateChat}
            disabled={creatingChat}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14m7-7H5" />
            </svg>
            {creatingChat ? 'Creating…' : 'New'}
          </button>

          {isOfferLetter && !isArchived && (
            <button
              onClick={handleSaveDraft}
              disabled={savingDraft}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {savingDraft ? 'Saving…' : 'Save Draft'}
            </button>
          )}

          {isReview && !isArchived && (
            <button
              onClick={handleOpenReviewRequestsModal}
              disabled={sendingReviewRequests}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {sendingReviewRequests ? 'Sending…' : 'Send Requests'}
            </button>
          )}

          {isWorkbook && !isArchived && (
            <button
              onClick={handleOpenHandbookSignatures}
              disabled={loadingActiveHandbooks || sendingHandbookSignatures}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {loadingActiveHandbooks ? 'Loading…' : sendingHandbookSignatures ? 'Sending…' : 'Send Signatures'}
            </button>
          )}

          {isWorkbook && !isArchived && !isFinalized && (
            <button
              onClick={handleGeneratePresentation}
              disabled={generatingPresentation}
              className="hidden sm:flex items-center px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 disabled:opacity-50 transition-all"
            >
              {generatingPresentation ? 'Generating…' : 'Presentation'}
            </button>
          )}

          {!isFinalized && !isArchived && !isUploadHandbook && (
            <button
              onClick={() => setShowFinalizeConfirm(true)}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs uppercase tracking-wider text-zinc-200 hover:text-white border border-white/20 hover:border-white/40 transition-all"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Finalize
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-400 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-red-300">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {isOutOfCredits && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-300 text-xs flex items-center justify-between gap-3">
          <span>Out of credits. Purchase more credits to continue using Matcha Work.</span>
          <button
            onClick={() => navigate('/app/matcha/work/billing')}
            className="px-2 py-1 border border-red-500/30 bg-red-600/20 hover:bg-red-600/40 text-red-100 uppercase tracking-wider transition-colors"
          >
            Open Billing
          </button>
        </div>
      )}

      {!isOutOfCredits && isLowCredits && (
        <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-xs flex items-center justify-between gap-3">
          <span>${creditBalance?.toFixed(2)} remaining — top up soon.</span>
          <button
            onClick={() => navigate('/app/matcha/work/billing')}
            className="px-2 py-1 border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-100 uppercase tracking-wider transition-colors"
          >
            Buy Credits
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Chat panel */}
        <div
          className={`flex flex-col flex-1 min-w-0 ${
            previewPanelOpen && hasPreviewContent ? 'md:max-w-[50%] border-r border-white/10' : ''
          } ${
            activeTab !== 'chat' ? 'hidden md:flex' : 'flex'
          }`}
        >
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-8">
                <div className="w-10 h-10 bg-matcha-600/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-matcha-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <p className="text-sm text-zinc-400 font-medium">Start chatting</p>
                <p className="text-xs text-zinc-600 mt-1 max-w-xs">
                  Tell me what you need in natural language.
                </p>

                {/* Quick action buttons */}
                {messages.length === 0 && !isFinalized && !isArchived && (
                  <div className="flex flex-wrap justify-center gap-2 mt-5 max-w-md">
                    {[
                      { label: 'Offer Letter', prompt: 'Create an offer letter', icon: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z' },
                      { label: 'Review', prompt: 'Write an anonymized performance review', icon: 'M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z' },
                      { label: 'Workbook', prompt: 'Create an HR workbook', icon: 'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25' },
                      { label: 'Onboarding', prompt: 'Create an employee onboarding plan', icon: 'M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z' },
                      { label: 'Handbook Template', prompt: 'Create an employee handbook', icon: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z' },
                      { label: 'Policy', prompt: 'Draft a workplace policy', icon: 'M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418' },
                      { label: 'Presentation', prompt: 'Create a presentation', icon: 'M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5' },
                    ].map((action) => (
                      <button
                        key={action.label}
                        type="button"
                        onClick={() => handleSend(action.prompt)}
                        className="flex items-center gap-1.5 px-3 py-1.5 border border-white/10 hover:border-white/25 bg-white/[0.03] hover:bg-white/[0.06] text-zinc-500 hover:text-zinc-300 transition-all text-[11px] tracking-wide"
                      >
                        <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d={action.icon} />
                        </svg>
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}

                {(isUnscopedChat || isHandbook) && !isFinalized && !isArchived && (
                  <div className="mt-4 w-full max-w-md">
                    <HandbookUpload
                      onUpload={handleHandbookUpload}
                      currentFilename={thread.current_state.handbook_uploaded_filename}
                    />
                  </div>
                )}

                <div className="mt-4 text-[11px] text-zinc-600 max-w-sm">
                  Ask naturally and Matcha will route commands when supported.
                </div>
                {isOfferLetter && !isFinalized && !isArchived && (
                  <LogoUpload
                    onUpload={handleLogoUpload}
                    currentLogoUrl={thread.current_state.company_logo_url}
                  />
                )}
              </div>
            ) : (
              <div className="space-y-1">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} msg={msg} />
                ))}
                {isOfferLetter && !isFinalized && !isArchived && (
                  <div className="mx-4 pb-4">
                    <LogoUpload
                      onUpload={handleLogoUpload}
                      currentLogoUrl={thread.current_state.company_logo_url}
                    />
                  </div>
                )}
                {isUploadHandbook && !isFinalized && !isArchived && (
                  <div className="mx-4 pb-4">
                    <HandbookUpload
                      onUpload={handleHandbookUpload}
                      currentFilename={thread.current_state.handbook_uploaded_filename}
                    />
                  </div>
                )}
              </div>
            )}
            {sending && (
              <div className="flex justify-start mb-3">
                <div className="w-7 h-7 bg-matcha-600 flex items-center justify-center mr-2 flex-shrink-0">
                  <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.5l1.196 4.784" />
                  </svg>
                </div>
                <div className="bg-zinc-800 border border-white/10 px-4 py-3">
                  <div className="flex gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-4 pb-4 pt-2 flex-shrink-0 border-t border-white/10">
            {(isFinalized || isArchived) ? (
              <div className="text-center py-3 text-xs text-zinc-500">
                This thread is {thread.status} — no further edits.
              </div>
            ) : (
              <>
              {selectedSlideIndex !== null && (() => {
                const slides = (isPresentation ? thread.current_state.slides : thread.current_state.presentation?.slides) || [];
                const slide = slides[selectedSlideIndex];
                const slideTitle = slide?.title || '';
                return (
                  <div className="flex items-center gap-2 mb-2">
                    <div className="flex items-center gap-1.5 bg-matcha-900/40 border border-matcha-500/30 px-2.5 py-1 text-[11px] text-matcha-400">
                      <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 0v10m0-10a2 2 0 012 2h2a2 2 0 012-2v0" />
                      </svg>
                      <span>Slide {selectedSlideIndex + 1}{slideTitle ? `: ${slideTitle}` : ''}</span>
                    </div>
                    <button
                      onClick={() => setSelectedSlideIndex(null)}
                      className="text-zinc-500 hover:text-zinc-300 transition-colors"
                      title="Clear slide selection"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })()}
              {!isUnscopedChat && messages.length > 0 && (() => {
                const skillBadge = isOfferLetter ? { label: 'Offer Letter', color: 'text-blue-400 border-blue-500/30 bg-blue-900/30' }
                  : isReview ? { label: 'Review', color: 'text-amber-400 border-amber-500/30 bg-amber-900/30' }
                  : isWorkbook ? { label: 'Workbook', color: 'text-emerald-400 border-emerald-500/30 bg-emerald-900/30' }
                  : isOnboarding ? { label: 'Onboarding', color: 'text-cyan-400 border-cyan-500/30 bg-cyan-900/30' }
                  : isHandbook ? { label: 'Handbook', color: 'text-orange-400 border-orange-500/30 bg-orange-900/30' }
                  : isPolicy ? { label: 'Policy', color: 'text-violet-400 border-violet-500/30 bg-violet-900/30' }
                  : isPresentation ? { label: 'Presentation', color: 'text-pink-400 border-pink-500/30 bg-pink-900/30' }
                  : null;
                if (!skillBadge) return null;
                return (
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] border ${skillBadge.color}`}>
                      {skillBadge.label}
                    </div>
                  </div>
                );
              })()}
              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={inputDisabled}
                  placeholder={
                    selectedSlideIndex !== null
                      ? `Edit slide ${selectedSlideIndex + 1} — describe your changes...`
                      : isUnscopedChat
                      ? 'Ask for an offer letter, review, workbook, onboarding, handbook, or policy...'
                      : isReview
                      ? 'Add anonymized review details...'
                      : isWorkbook
                      ? 'Describe workbook sections or objective...'
                      : isOnboarding
                      ? 'Add employee details or confirm to create...'
                      : isHandbook
                      ? 'Describe your company for the handbook...'
                      : isPolicy
                      ? 'Describe the policy type and locations...'
                      : 'Describe changes or add details...'
                  }
                  rows={1}
                  className="flex-1 bg-zinc-900 border border-white/10 light:bg-black/[0.04] light:focus:bg-white/20 light:border-white/30 light:backdrop-blur-[40px] light:shadow-[inset_0_2px_8px_rgba(0,0,0,0.04)] px-3.5 py-2.5 text-sm text-zinc-200 light:text-zinc-900 placeholder-zinc-500 light:placeholder-zinc-500/70 resize-none focus:outline-none focus:border-white/20 light:focus:border-zinc-400 disabled:opacity-50 transition-all rounded-sm"
                  style={{ minHeight: '42px', maxHeight: '120px' }}
                  onInput={(e) => {
                    const t = e.currentTarget;
                    t.style.height = 'auto';
                    t.style.height = `${Math.min(t.scrollHeight, 120)}px`;
                  }}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={inputDisabled || !input.trim()}
                  className="w-10 h-10 flex items-center justify-center bg-matcha-600 hover:bg-matcha-700 light:bg-black light:hover:bg-black/80 light:shadow-md disabled:opacity-40 transition-colors flex-shrink-0 rounded-sm"
                >
                  <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              </div>
              </>
            )}
          </div>
        </div>

        {/* PDF preview panel */}
        <div
          className={`flex flex-col flex-1 min-w-0 ${
            !(previewPanelOpen && hasPreviewContent)
              ? 'hidden'
              : activeTab !== 'preview'
              ? 'hidden md:flex'
              : 'flex'
          }`}
        >
          {/* PDF toolbar */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 flex-shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowVersions((prev) => !prev)}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                v{thread.version}
                <svg className={`w-3 h-3 transition-transform ${showVersions ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
            <div className="flex items-center gap-2">
              {isOfferLetter && pdfUrl && (
                <a
                  href={pdfUrl}
                  download={`${thread.title}.pdf`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download
                </a>
              )}
              {hasPresentationPreviewContent && (
                <button
                  onClick={() => matchaWork.downloadPresentationPdf(thread.id, thread.current_state.presentation_title || 'presentation')}
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download PDF
                </button>
              )}
            </div>
          </div>

          {/* Version list dropdown */}
          {showVersions && (
            <div className="border-b border-white/10 bg-zinc-950 max-h-48 overflow-y-auto">
              {loadingVersions ? (
                <div className="px-4 py-3 text-xs text-zinc-500">Loading versions...</div>
              ) : versions.length === 0 ? (
                <div className="px-4 py-3 text-xs text-zinc-500">No versions yet</div>
              ) : (
                versions.map((ver) => (
                  <div
                    key={ver.id}
                    className="flex items-center justify-between px-4 py-2 hover:bg-zinc-800/30 border-b border-white/5"
                  >
                    <div>
                      <span className="text-xs font-medium text-zinc-300">v{ver.version}</span>
                      {ver.diff_summary && (
                        <span className="ml-2 text-xs text-zinc-500">{ver.diff_summary}</span>
                      )}
                      <div className="text-xs text-zinc-600 mt-0.5">
                        {new Date(ver.created_at).toLocaleString()}
                      </div>
                    </div>
                    {ver.version !== thread.version && !isFinalized && (
                      <button
                        onClick={() => handleRevert(ver.version)}
                        className="text-xs text-matcha-400 hover:text-matcha-300 transition-colors"
                      >
                        Revert
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* PDF iframe */}
          <div className="flex-1 bg-zinc-900 light:bg-black/[0.12] light:backdrop-blur-md min-h-0 transition-colors">
            {previewKind === 'offer_letter' ? (
              pdfBlobUrl ? (
                <iframe
                  src={pdfBlobUrl}
                  className="w-full h-full border-0"
                  title="Offer Letter Preview"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center py-8">
                  <div className="w-12 h-12 bg-zinc-800 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] flex items-center justify-center mb-3 transition-colors">
                    <svg className="w-6 h-6 text-zinc-600 light:text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <p className="text-sm text-zinc-500 light:text-zinc-500">
                    {pdfUrl ? 'Loading preview...' : 'Preview will appear here as you add details'}
                  </p>
                </div>
              )
            ) : previewKind === 'presentation' ? (
              <PresentationPreview
                state={thread.current_state}
                threadId={thread.id}
                selectedSlideIndex={selectedSlideIndex}
                onSelectSlide={!isFinalized && !isArchived ? setSelectedSlideIndex : undefined}
              />
            ) : previewKind === 'workbook' ? (
              <WorkbookPreview
                state={thread.current_state}
                threadId={thread.id}
                selectedSlideIndex={selectedSlideIndex}
                onSelectSlide={!isFinalized && !isArchived ? setSelectedSlideIndex : undefined}
              />
            ) : previewKind === 'handbook' ? (
              <HandbookPreview state={thread.current_state} />
            ) : previewKind === 'policy' ? (
              <PolicyPreview state={thread.current_state} />
            ) : previewKind === 'onboarding' ? (
              <OnboardingPreview state={thread.current_state} />
            ) : (
              <div className="h-full overflow-y-auto p-4">
                <div className="max-w-2xl mx-auto bg-zinc-950 border border-white/10 light:bg-white/20 light:backdrop-blur-[40px] light:backdrop-saturate-[150%] light:border-white/40 light:shadow-[0_4px_16px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,0.5)] light:shadow-sm p-4 space-y-4 transition-colors">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-500 light:text-zinc-500">Anonymous Review</p>
                    <h3 className="text-base font-semibold text-zinc-100 mt-1">
                      {thread.current_state.review_title || thread.current_state.review_subject || 'Untitled Review'}
                    </h3>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs bg-zinc-800 border border-white/10 text-zinc-200 px-2 py-0.5">
                        {thread.current_state.anonymized === false ? 'Not anonymized' : 'Anonymized'}
                      </span>
                      {thread.current_state.overall_rating != null && (
                        <span className="text-xs bg-amber-500/10 border border-amber-500/20 text-amber-300 px-2 py-0.5">
                          Rating: {thread.current_state.overall_rating}/5
                        </span>
                      )}
                    </div>
                  </div>

                  {(thread.current_state.summary || thread.current_state.context) && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Summary</p>
                      <p className="text-sm text-zinc-200 whitespace-pre-wrap">
                        {thread.current_state.summary || thread.current_state.context}
                      </p>
                    </div>
                  )}

                  {reviewStrengths.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Strengths</p>
                      <ul className="space-y-1">
                        {reviewStrengths.map((item, idx) => (
                          <li key={`${item}-${idx}`} className="text-sm text-zinc-200">
                            • {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {reviewGrowthAreas.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Growth Areas</p>
                      <ul className="space-y-1">
                        {reviewGrowthAreas.map((item, idx) => (
                          <li key={`${item}-${idx}`} className="text-sm text-zinc-200">
                            • {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {thread.current_state.next_steps && (
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Next Steps</p>
                      <p className="text-sm text-zinc-200 whitespace-pre-wrap">
                        {thread.current_state.next_steps}
                      </p>
                    </div>
                  )}

                  <div>
                    <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Response Tracking</p>
                    <div className="grid grid-cols-3 gap-px bg-white/10 border border-white/10">
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Expected</p>
                        <p className="text-sm font-mono text-zinc-200 mt-0.5">{reviewExpectedResponses}</p>
                      </div>
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Received</p>
                        <p className="text-sm font-mono text-emerald-300 mt-0.5">{reviewReceivedResponses}</p>
                      </div>
                      <div className="bg-zinc-950 p-2">
                        <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Pending</p>
                        <p className="text-sm font-mono text-amber-300 mt-0.5">{reviewPendingResponses}</p>
                      </div>
                    </div>
                    {reviewStatuses.length > 0 ? (
                      <div className="mt-3 space-y-1.5">
                        {reviewStatuses.map((row) => (
                          <div
                            key={row.email}
                            className="flex items-center justify-between border border-white/10 bg-zinc-950 px-2.5 py-2"
                          >
                            <div className="min-w-0">
                              <p className="text-xs text-zinc-300 truncate">{row.email}</p>
                              {row.submitted_at && (
                                <p className="text-[11px] text-zinc-500 mt-0.5">
                                  Submitted {new Date(row.submitted_at).toLocaleString()}
                                </p>
                              )}
                              {!row.submitted_at && row.sent_at && (
                                <p className="text-[11px] text-zinc-500 mt-0.5">
                                  Sent {new Date(row.sent_at).toLocaleString()}
                                </p>
                              )}
                              {row.status === 'failed' && row.last_error && (
                                <p className="text-[11px] text-red-400 mt-0.5">Error: {row.last_error}</p>
                              )}
                            </div>
                            <span
                              className={`ml-3 text-[10px] px-1.5 py-0.5 uppercase tracking-wider border ${
                                row.status === 'submitted'
                                  ? 'border-emerald-500/20 text-emerald-300'
                                  : row.status === 'sent'
                                  ? 'border-blue-500/20 text-blue-300'
                                  : row.status === 'failed'
                                  ? 'border-red-500/20 text-red-300'
                                  : 'border-amber-500/20 text-amber-300'
                              }`}
                            >
                              {row.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-500 mt-2">
                        No recipients yet. Use Send Requests to distribute this review.
                      </p>
                    )}
                  </div>

                  {!thread.current_state.summary &&
                    !thread.current_state.context &&
                    reviewStrengths.length === 0 &&
                    reviewGrowthAreas.length === 0 &&
                    !thread.current_state.next_steps && (
                      <div className="border border-white/10 bg-zinc-950 p-3">
                        <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                          Starter Template
                        </p>
                        <ul className="space-y-1 text-sm text-zinc-400">
                          <li>Summary: Add a concise overview of overall performance.</li>
                          <li>Strengths: List key wins, impact, and standout behaviors.</li>
                          <li>Growth Areas: Add focused improvement opportunities.</li>
                          <li>Next Steps: Add action items, owner, and check-in timing.</li>
                        </ul>
                      </div>
                    )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {showHandbookSelectorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">Select Handbook</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Choose an active handbook to send for acknowledgement signatures.
            </p>
            <div className="max-h-72 overflow-y-auto space-y-1">
              {activeHandbooks.map((handbook) => (
                <button
                  key={handbook.id}
                  onClick={() => handleSelectHandbookForSignatures(handbook)}
                  className="w-full text-left border border-white/10 hover:border-white/20 bg-zinc-900 hover:bg-zinc-800 px-3 py-2 transition-colors"
                >
                  <p className="text-sm text-zinc-100">{handbook.title}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    v{handbook.active_version} · {handbook.scope_states?.join(', ') || 'N/A'}
                  </p>
                </button>
              ))}
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowHandbookSelectorModal(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <HandbookDistributeModal
        open={showHandbookDistributeModal}
        handbookId={selectedHandbook?.id ?? null}
        handbookTitle={selectedHandbook?.title}
        submitting={sendingHandbookSignatures}
        onClose={() => {
          if (!sendingHandbookSignatures) setShowHandbookDistributeModal(false);
        }}
        onSubmit={handleSendHandbookSignatures}
      />

      {/* Review requests modal */}
      {showReviewRequestsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-lg w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">Send Anonymous Review Requests</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Add recipient emails. Each recipient will get a unique link and tracking updates will appear in this thread.
            </p>
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Recipient Emails</span>
              <textarea
                value={reviewRecipientInput}
                onChange={(e) => setReviewRecipientInput(e.target.value)}
                placeholder="manager@company.com, peer@company.com"
                rows={4}
                className="mt-1 w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-white/20"
              />
            </label>
            <label className="block mt-3">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Optional Message</span>
              <textarea
                value={reviewEmailMessage}
                onChange={(e) => setReviewEmailMessage(e.target.value)}
                placeholder="Add context for reviewers..."
                rows={3}
                className="mt-1 w-full bg-zinc-900 border border-white/10 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-white/20"
              />
            </label>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => setShowReviewRequestsModal(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSendReviewRequests}
                disabled={sendingReviewRequests}
                className="flex-1 px-4 py-2 text-sm bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white transition-colors flex items-center justify-center gap-2"
              >
                {sendingReviewRequests ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : null}
                Send Requests
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Finalize confirm modal */}
      {showFinalizeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-950 border border-white/10 p-6 max-w-sm w-full mx-4 shadow-xl">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-2">
              {isOfferLetter ? 'Finalize offer letter?' : isWorkbook ? 'Finalize workbook?' : isOnboarding ? 'Finalize onboarding?' : isHandbook ? 'Finalize handbook?' : 'Finalize anonymous review?'}
            </h2>
            <p className="text-sm text-zinc-400 mb-5">
              {isOfferLetter
                ? "This will lock the document and generate a final PDF without a watermark. You won't be able to make further edits."
                : isWorkbook
                ? "This will lock the workbook and prevent further edits. You can still view the content here."
                : isOnboarding
                ? "This will lock the onboarding thread. Created employees will remain in the system."
                : isHandbook
                ? "This will lock the handbook and prevent further edits. You can still view and distribute it."
                : "This will lock the review and prevent further edits. You can still view the final thread content."}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowFinalizeConfirm(false)}
                className="flex-1 px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleFinalize}
                disabled={finalizing}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white transition-colors flex items-center justify-center gap-2"
              >
                {finalizing ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : null}
                Finalize
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

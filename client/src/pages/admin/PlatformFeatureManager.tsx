import { useState, useCallback } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import { useDroppable, useDraggable } from '@dnd-kit/core';
import { X, GripVertical } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { adminPlatformSettings } from '../../api/client';

interface Props {
  onClose: () => void;
}

const SECTION_MAP: Record<string, string> = {
  admin_overview: 'Platform', client_management: 'Platform', company_features: 'Platform',
  industry_handbooks: 'Platform', admin_import: 'Platform',
  projects: 'Recruiting', interviewer: 'Recruiting', candidate_metrics: 'Recruiting',
  interview_prep: 'Recruiting', test_bot: 'Recruiting',
  onboarding: 'HR', employees: 'HR', offer_letters: 'HR', policies: 'HR',
  handbooks: 'HR', time_off: 'HR', accommodations: 'HR', internal_mobility: 'HR',
  matcha_work: 'HR',
  er_copilot: 'HR', incidents: 'HR',
  xp_dashboard: 'Employee XP', vibe_checks: 'Employee XP', enps: 'Employee XP',
  performance_reviews: 'Employee XP',
  compliance: 'Compliance', jurisdictions: 'Compliance',
  blog: 'Content', hr_news: 'Content',
};

const SIDEBAR_SECTIONS = ['Platform', 'Recruiting', 'HR', 'Employee XP', 'Compliance', 'Content'];

const ALL_FEATURES = Object.keys(SECTION_MAP);

const FEATURE_META: Record<string, { label: string; clientGated: boolean }> = {
  admin_overview: { label: 'Overview', clientGated: false },
  client_management: { label: 'Registrations', clientGated: false },
  company_features: { label: 'Company Features', clientGated: false },
  industry_handbooks: { label: 'Industry Handbooks', clientGated: false },
  admin_import: { label: 'Import', clientGated: false },
  projects: { label: 'Projects', clientGated: false },
  interviewer: { label: 'Interviewer', clientGated: false },
  candidate_metrics: { label: 'Candidate Metrics', clientGated: false },
  interview_prep: { label: 'Interview Prep Beta', clientGated: true },
  test_bot: { label: 'Test Bot', clientGated: false },
  onboarding: { label: 'Onboarding', clientGated: false },
  employees: { label: 'Employees', clientGated: true },
  offer_letters: { label: 'Offer Letters', clientGated: true },
  matcha_work: { label: 'Matcha Work', clientGated: true },
  policies: { label: 'Policies', clientGated: true },
  handbooks: { label: 'Handbooks', clientGated: true },
  time_off: { label: 'Time Off + Leave', clientGated: true },
  accommodations: { label: 'Accommodations', clientGated: true },
  internal_mobility: { label: 'Internal Mobility', clientGated: true },
  er_copilot: { label: 'ER Copilot', clientGated: true },
  incidents: { label: 'Incidents', clientGated: true },
  xp_dashboard: { label: 'XP Dashboard', clientGated: false },
  vibe_checks: { label: 'Vibe Checks', clientGated: true },
  enps: { label: 'eNPS Surveys', clientGated: true },
  performance_reviews: { label: 'Performance Reviews', clientGated: true },
  compliance: { label: 'Compliance', clientGated: true },
  jurisdictions: { label: 'Jurisdictions', clientGated: false },
  blog: { label: 'Blog', clientGated: false },
  hr_news: { label: 'HR News', clientGated: false },
};

function DraggableCard({ featureKey, compact = false }: { featureKey: string; compact?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: featureKey });
  const meta = FEATURE_META[featureKey] || { label: featureKey, clientGated: false };
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;

  return (
    <div
      ref={setNodeRef}
      style={{ ...style, opacity: isDragging ? 0.4 : 1 }}
      className={`flex items-center gap-2 px-3 py-2 bg-zinc-900 border border-white/5 select-none ${compact ? '' : 'w-full'}`}
    >
      <button
        {...attributes}
        {...listeners}
        className="text-zinc-700 hover:text-zinc-500 cursor-grab active:cursor-grabbing touch-none"
      >
        <GripVertical className="w-3 h-3" />
      </button>
      <span className="flex-1 text-[10px] tracking-wide text-zinc-300 truncate">{meta.label}</span>
      {meta.clientGated && (
        <span className="text-[8px] text-zinc-600 tracking-wide shrink-0">client</span>
      )}
    </div>
  );
}

function DroppableZone({ id, children, className }: { id: string; children: React.ReactNode; className?: string }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
      className={`${className || ''} ${isOver ? 'bg-white/5' : ''} transition-colors min-h-24`}
    >
      {children}
    </div>
  );
}

export function PlatformFeatureManager({ onClose }: Props) {
  const { platformFeatures, setPlatformFeatures } = useAuth();
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set(platformFeatures));
  const [modelMode, setModelMode] = useState<'light' | 'heavy'>('light');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial settings
  useState(() => {
    setLoading(true);
    adminPlatformSettings.get()
      .then(data => {
        setModelMode(data.matcha_work_model_mode as 'light' | 'heavy');
      })
      .catch(() => {
        // Fallback if settings don't exist yet
        setModelMode('light');
      })
      .finally(() => setLoading(false));
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const shelvedFeatures = ALL_FEATURES.filter(k => !activeKeys.has(k));

  const activeBySection = SIDEBAR_SECTIONS.reduce<Record<string, string[]>>((acc, section) => {
    acc[section] = ALL_FEATURES.filter(k => activeKeys.has(k) && SECTION_MAP[k] === section);
    return acc;
  }, {});

  const onDragStart = useCallback((event: DragStartEvent) => {
    setDraggingId(event.active.id as string);
  }, []);

  const onDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    setDraggingId(null);
    if (!over) return;

    const draggedKey = active.id as string;
    const wasActive = activeKeys.has(draggedKey);
    const overId = over.id as string;

    const overIsShelved = overId === 'shelved-panel' || (!activeKeys.has(overId) && overId !== 'active-panel' && ALL_FEATURES.includes(overId));
    const overIsActive = overId === 'active-panel' || activeKeys.has(overId);

    if (overIsShelved && wasActive) {
      setActiveKeys(prev => {
        const next = new Set(prev);
        next.delete(draggedKey);
        return next;
      });
    } else if (overIsActive && !wasActive) {
      setActiveKeys(prev => new Set([...prev, draggedKey]));
    }
  }, [activeKeys]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const [featuresResult] = await Promise.all([
        adminPlatformSettings.update(Array.from(activeKeys)),
        adminPlatformSettings.updateMatchaWorkModelMode(modelMode),
      ]);
      setPlatformFeatures(new Set(featuresResult.visible_features));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="w-full max-w-4xl h-[80vh] bg-zinc-950 border border-white/10 flex flex-col shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 shrink-0">
            <div>
              <h2 className="text-xs tracking-[0.2em] uppercase text-white font-bold">Platform Features</h2>
              <p className="text-[10px] text-zinc-500 mt-0.5">Drag features to activate or shelve them</p>
            </div>
            <button
              onClick={onClose}
              className="text-zinc-500 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 flex overflow-hidden">
            {/* Left: Active */}
            <div className="w-1/2 border-r border-white/10 flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 shrink-0">
                <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-400">In Sidebar</span>
                <span className="ml-2 text-[9px] text-zinc-600">{activeKeys.size} active</span>
              </div>
              <DroppableZone id="active-panel" className="flex-1 overflow-y-auto p-4 space-y-4">
                {SIDEBAR_SECTIONS.map(sectionName => {
                  const items = activeBySection[sectionName] || [];
                  if (items.length === 0) return null;
                  return (
                    <div key={sectionName}>
                      <div className="text-[8px] tracking-[0.2em] uppercase text-zinc-600 mb-2 px-1">
                        {sectionName} <span className="text-zinc-700">({items.length})</span>
                      </div>
                      <div className="space-y-1">
                        {items.map(key => (
                          <DraggableCard key={key} featureKey={key} />
                        ))}
                      </div>
                    </div>
                  );
                })}
                {activeKeys.size === 0 && (
                  <div className="text-[10px] text-zinc-700 text-center py-8">
                    Drag features here to activate them
                  </div>
                )}
              </DroppableZone>
            </div>

            {/* Right: Shelved */}
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 shrink-0">
                <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-400">Available Features</span>
                <span className="ml-2 text-[9px] text-zinc-600">{shelvedFeatures.length} shelved</span>
              </div>
              <DroppableZone id="shelved-panel" className="flex-1 overflow-y-auto p-4">
                <div className="grid grid-cols-2 gap-2">
                  {shelvedFeatures.map(key => (
                    <DraggableCard key={key} featureKey={key} compact />
                  ))}
                </div>
                {shelvedFeatures.length === 0 && (
                  <div className="text-[10px] text-zinc-700 text-center py-8">
                    All features are active
                  </div>
                )}
              </DroppableZone>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-white/10 shrink-0">
            <div className="flex items-center gap-8">
              <div className="text-[10px] text-zinc-600">
                {activeKeys.size} of {ALL_FEATURES.length} features active
              </div>
              
              <div className="flex items-center gap-3">
                <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-500 font-bold">Matcha Work AI:</span>
                <div className="flex bg-zinc-900 border border-white/5 p-0.5 rounded">
                  <button
                    onClick={() => setModelMode('light')}
                    className={`px-3 py-1 text-[9px] tracking-[0.1em] uppercase transition-all ${modelMode === 'light' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    Light
                  </button>
                  <button
                    onClick={() => setModelMode('heavy')}
                    className={`px-3 py-1 text-[9px] tracking-[0.1em] uppercase transition-all ${modelMode === 'heavy' ? 'bg-zinc-800 text-white font-bold' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    Heavy
                  </button>
                </div>
              </div>
              
              {error && <span className="text-red-400 text-[10px] font-mono">{error}</span>}
              {loading && <span className="text-zinc-600 text-[10px] font-mono animate-pulse">Loading settings...</span>}
            </div>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase bg-white text-black hover:bg-zinc-200 transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>

        <DragOverlay>
          {draggingId && (
            <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800 border border-white/20 shadow-2xl text-[10px] text-zinc-200 tracking-wide">
              <GripVertical className="w-3 h-3 text-zinc-500" />
              {FEATURE_META[draggingId]?.label || draggingId}
            </div>
          )}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

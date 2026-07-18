import type { ProjectPanelController } from './useProjectPanel'

export default function PanelTabs({ ctl }: { ctl: ProjectPanelController }) {
  const { panelTab, setPanelTab } = ctl
  return (
    <div className="flex" style={{ borderBottom: '1px solid #333' }}>
      {(['sections', 'research'] as const).map(tab => (
        <button
          key={tab}
          onClick={() => setPanelTab(tab)}
          className="px-4 py-1.5 text-[10px] uppercase tracking-widest font-bold transition-colors"
          style={{
            color: panelTab === tab ? '#e8e8e8' : '#6a737d',
            background: panelTab === tab ? '#252526' : 'transparent',
            borderBottom: panelTab === tab ? '2px solid #ce9178' : '2px solid transparent',
          }}
        >
          {tab === 'sections' ? 'Sections' : 'Research'}
        </button>
      ))}
    </div>
  )
}

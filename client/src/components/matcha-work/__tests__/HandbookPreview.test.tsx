import { useRef, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { HandbookPreview } from '../HandbookPreview';
import type { MWDocumentState } from '../../../types/matcha-work';
import { render, screen } from '../../../test/utils';

const handbookState: MWDocumentState = {
  handbook_title: 'Retail Employee Handbook',
  handbook_source_type: 'template',
  handbook_status: 'ready',
  handbook_mode: 'multi_state',
  handbook_industry: 'retail',
  handbook_sub_industry: 'luxury',
  handbook_states: ['CA', 'NY'],
  handbook_legal_name: 'Matcha Retail LLC',
  handbook_dba: 'Matcha',
  handbook_ceo: 'Avery Finch',
  handbook_headcount: 42,
  handbook_profile: {
    remote_workers: true,
    minors: false,
    hourly_employees: true,
    salaried_employees: true,
  },
  handbook_strength_score: 88,
  handbook_strength_label: 'Strong',
  handbook_sections: [
    {
      section_key: 'welcome',
      title: 'Welcome',
      content: 'Welcome to Matcha. This section is intentionally long enough to resemble real handbook content.',
    },
    {
      section_key: 'attendance',
      title: 'Attendance',
      content: 'Employees are expected to report to work on time and follow local scheduling requirements.',
    },
  ],
};

function HandbookPreviewHarness({ onRender }: { onRender: () => void }) {
  const [input, setInput] = useState('');
  const stableState = useRef(handbookState).current;

  return (
    <div>
      <label htmlFor="chat-input">Chat input</label>
      <input
        id="chat-input"
        value={input}
        onChange={(event) => setInput(event.target.value)}
      />
      <HandbookPreview state={stableState} onRender={onRender} />
    </div>
  );
}

describe('HandbookPreview', () => {
  it('does not rerender when sibling chat input changes with stable handbook state', async () => {
    const onRender = vi.fn();
    const { user } = render(<HandbookPreviewHarness onRender={onRender} />, { withRouter: false });

    expect(screen.getByText('Retail Employee Handbook')).toBeInTheDocument();
    expect(screen.getByText('2 Sections')).toBeInTheDocument();
    expect(onRender).toHaveBeenCalledTimes(1);

    await user.type(screen.getByLabelText('Chat input'), 'slow');

    expect(onRender).toHaveBeenCalledTimes(1);
  });
});

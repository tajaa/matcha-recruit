import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '../../test/utils';
import HandbookForm from '../HandbookForm';

const handbooksMock = vi.hoisted(() => ({
  getProfile: vi.fn(),
  get: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  uploadFile: vi.fn(),
}));

const complianceApiMock = vi.hoisted(() => ({
  getLocations: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  handbooks: handbooksMock,
}));

vi.mock('../../api/compliance', () => ({
  complianceAPI: complianceApiMock,
}));

vi.mock('../../features/feature-guides', () => ({
  FeatureGuideTrigger: () => null,
}));

describe('HandbookForm (edit mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    handbooksMock.getProfile.mockResolvedValue(null);
    complianceApiMock.getLocations.mockResolvedValue([]);
    handbooksMock.update.mockResolvedValue({ id: 'hb-1' });
    handbooksMock.get.mockResolvedValue({
      id: 'hb-1',
      company_id: 'co-1',
      title: 'Employee Handbook',
      status: 'draft',
      mode: 'single_state',
      source_type: 'template',
      active_version: 1,
      file_url: '/uploads/resumes/generated.pdf',
      file_name: 'generated.pdf',
      scopes: [
        {
          id: 'scope-1',
          state: 'CA',
          city: 'Los Angeles',
          zipcode: '90001',
          location_id: 'loc-1',
        },
      ],
      profile: {
        legal_name: 'Acme LLC',
        dba: null,
        ceo_or_president: 'Alex Founder',
        headcount: 15,
        remote_workers: true,
        minors: false,
        tipped_employees: false,
        union_employees: false,
        federal_contracts: false,
        group_health_insurance: true,
        background_checks: true,
        hourly_employees: true,
        salaried_employees: true,
        commissioned_employees: false,
        tip_pooling: false,
      },
      sections: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      published_at: null,
      created_by: null,
    });
  });

  it('renders source as read-only in edit mode and preserves scope metadata on update', async () => {
    const { user } = render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/hb-1/edit']}>
        <Routes>
          <Route path="/app/matcha/handbook/:id/edit" element={<HandbookForm />} />
          <Route path="/app/matcha/handbook/:id" element={<div>Handbook Detail</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await waitFor(() => expect(screen.getByDisplayValue('Employee Handbook')).toBeInTheDocument());

    expect(screen.getByText('Template Builder')).toBeInTheDocument();
    expect(screen.getByText('Answer each question with Yes or No')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(2);

    await user.click(screen.getByRole('button', { name: 'Update Handbook' }));

    await waitFor(() => expect(handbooksMock.update).toHaveBeenCalledTimes(1));
    const [, payload] = handbooksMock.update.mock.calls[0];

    expect(payload.scopes).toEqual([
      {
        state: 'CA',
        city: 'Los Angeles',
        zipcode: '90001',
        location_id: 'loc-1',
      },
    ]);
    expect(payload).not.toHaveProperty('file_url');
    expect(payload).not.toHaveProperty('file_name');
  });
});

describe('HandbookForm (create wizard)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    handbooksMock.getProfile.mockResolvedValue(null);
    complianceApiMock.getLocations.mockResolvedValue([]);
    handbooksMock.create.mockResolvedValue({ id: 'hb-new' });
  });

  it('shows one question at a time and branches by source type', async () => {
    const { user } = render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/new']}>
        <Routes>
          <Route path="/app/matcha/handbook/new" element={<HandbookForm />} />
          <Route path="/app/matcha/handbook/:id" element={<div>Handbook Detail</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    expect(screen.getByText('What should this handbook be called?')).toBeInTheDocument();
    expect(screen.getByText('Helper Guidance')).toBeInTheDocument();
    expect(screen.getByText(/This is the admin-visible name for your draft handbook/i)).toBeInTheDocument();
    expect(screen.queryByText('Which industry best matches this business?')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Title is required')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('e.g. 2026 Employee Handbook'), 'Wizard Handbook');
    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('Is this handbook single-state or multi-state?')).toBeInTheDocument();
    expect(screen.getByText(/Defines whether this draft governs one state or multiple states/i)).toBeInTheDocument();
    expect(screen.queryByText('What should this handbook be called?')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Start from Matcha template boilerplate or upload your own handbook?')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Upload Existing Handbook/i }));
    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('Select the state for this handbook')).toBeInTheDocument();
    expect(screen.queryByText('Which industry best matches this business?')).not.toBeInTheDocument();
  });

  it('shows industry and jurisdiction-specific helper guidance', async () => {
    const { user } = render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/new']}>
        <Routes>
          <Route path="/app/matcha/handbook/new" element={<HandbookForm />} />
          <Route path="/app/matcha/handbook/:id" element={<div>Handbook Detail</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await user.type(screen.getByPlaceholderText('e.g. 2026 Employee Handbook'), 'CA Tech Handbook');
    await user.click(screen.getByRole('button', { name: 'Next' })); // mode
    await user.click(screen.getByRole('button', { name: 'Next' })); // source
    await user.click(screen.getByRole('button', { name: 'Next' })); // industry

    await user.selectOptions(screen.getByRole('combobox'), 'technology');
    expect(screen.getByText(/For technology employers, handbook logic emphasizes remote\/hybrid operations/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' })); // sub industry
    await user.click(screen.getByRole('button', { name: 'Next' })); // states

    await user.click(screen.getByRole('button', { name: 'CA' }));
    expect(screen.getByText(/CA generally requires stricter wage\/hour, break, and reimbursement handling/i)).toBeInTheDocument();
    expect(screen.getByText(/For a CA tech startup, classify exempt\/non-exempt roles conservatively/i)).toBeInTheDocument();
  });

  it('does not append hospitality overlays to company identity cards', async () => {
    const { user } = render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/new']}>
        <Routes>
          <Route path="/app/matcha/handbook/new" element={<HandbookForm />} />
          <Route path="/app/matcha/handbook/:id" element={<div>Handbook Detail</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await user.type(screen.getByPlaceholderText('e.g. 2026 Employee Handbook'), 'Hospitality Handbook');
    await user.click(screen.getByRole('button', { name: 'Next' })); // mode
    await user.click(screen.getByRole('button', { name: 'Next' })); // source
    await user.click(screen.getByRole('button', { name: 'Next' })); // industry
    await user.selectOptions(screen.getByRole('combobox'), 'hospitality');
    await user.click(screen.getByRole('button', { name: 'Next' })); // sub industry
    await user.click(screen.getByRole('button', { name: 'Next' })); // states
    await user.click(screen.getByRole('button', { name: 'CA' })); // states selection
    await user.click(screen.getByRole('button', { name: 'Next' })); // legal name card

    expect(screen.getByText(/This legal entity name appears in formal policy language/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/For hospitality, handbook logic prioritizes tipped-workforce and shift-operations controls/i)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/CA generally requires stricter wage\/hour, break, and reimbursement handling/i)
    ).not.toBeInTheDocument();
  });

  it('shows recovery actions for missing boilerplate coverage errors', async () => {
    handbooksMock.create.mockRejectedValueOnce(
      new Error('Missing required state boilerplate coverage for hospitality handbook generation: Illinois')
    );

    const { user } = render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/new']}>
        <Routes>
          <Route path="/app/matcha/handbook/new" element={<HandbookForm />} />
          <Route path="/app/matcha/compliance" element={<div>Compliance Page</div>} />
          <Route path="/app/matcha/handbook/:id" element={<div>Handbook Detail</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await user.type(screen.getByPlaceholderText('e.g. 2026 Employee Handbook'), 'Coverage Test Handbook');

    // Advance to state selection.
    await user.click(screen.getByRole('button', { name: 'Next' })); // mode
    await user.click(screen.getByRole('button', { name: 'Next' })); // source
    await user.click(screen.getByRole('button', { name: 'Next' })); // industry
    await user.click(screen.getByRole('button', { name: 'Next' })); // sub industry
    await user.click(screen.getByRole('button', { name: 'Next' })); // states
    await user.click(screen.getByRole('button', { name: 'CA' }));
    await user.click(screen.getByRole('button', { name: 'Next' })); // legal name

    await user.type(screen.getByRole('textbox'), 'Acme LLC');
    await user.click(screen.getByRole('button', { name: 'Next' })); // dba
    await user.click(screen.getByRole('button', { name: 'Next' })); // ceo
    await user.type(screen.getByRole('textbox'), 'Alex Founder');
    await user.click(screen.getByRole('button', { name: 'Next' })); // headcount
    await user.click(screen.getByRole('button', { name: 'Next' })); // remote_workers
    await user.click(screen.getByRole('button', { name: 'Next' })); // minors
    await user.click(screen.getByRole('button', { name: 'Next' })); // tipped_employees
    await user.click(screen.getByRole('button', { name: 'Next' })); // union_employees
    await user.click(screen.getByRole('button', { name: 'Next' })); // federal_contracts
    await user.click(screen.getByRole('button', { name: 'Next' })); // group_health_insurance
    await user.click(screen.getByRole('button', { name: 'Next' })); // background_checks
    await user.click(screen.getByRole('button', { name: 'Next' })); // hourly_employees
    await user.click(screen.getByRole('button', { name: 'Next' })); // salaried_employees
    await user.click(screen.getByRole('button', { name: 'Next' })); // commissioned_employees
    await user.click(screen.getByRole('button', { name: 'Next' })); // policy_pack
    await user.click(screen.getByRole('button', { name: 'Next' })); // custom_sections
    await user.click(screen.getByRole('button', { name: 'Next' })); // review

    await user.click(screen.getByRole('button', { name: 'Create Handbook' }));

    await waitFor(() =>
      expect(screen.getByText(/Missing required state boilerplate coverage/i)).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: 'Go To Policy Pack' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Compliance' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Go To Policy Pack' }));
    expect(screen.getByText('Generate required boilerplate and guided follow-ups')).toBeInTheDocument();
  });
});

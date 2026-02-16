import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '../../test/utils';
import HandbookDetail from '../HandbookDetail';

const handbooksMock = vi.hoisted(() => ({
  get: vi.fn(),
  listChanges: vi.fn(),
  acknowledgements: vi.fn(),
  update: vi.fn(),
  publish: vi.fn(),
  archive: vi.fn(),
  downloadPdf: vi.fn(),
  distribute: vi.fn(),
  acceptChange: vi.fn(),
  rejectChange: vi.fn(),
}));

vi.mock('../../api/client', () => ({
  handbooks: handbooksMock,
}));

describe('HandbookDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    handbooksMock.get.mockRejectedValue(new Error('Failed to load handbook detail'));
    handbooksMock.listChanges.mockResolvedValue([]);
    handbooksMock.acknowledgements.mockResolvedValue(null);
  });

  it('shows a recoverable error state when initial load fails', async () => {
    render(
      <MemoryRouter initialEntries={['/app/matcha/handbook/hb-1']}>
        <Routes>
          <Route path="/app/matcha/handbook/:id" element={<HandbookDetail />} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await waitFor(() => {
      expect(screen.getByText('Failed to load handbook detail')).toBeInTheDocument();
    });
    expect(screen.queryByText('Loading handbook...')).not.toBeInTheDocument();
    expect(screen.getByText('Back to Handbooks')).toBeInTheDocument();
  });
});

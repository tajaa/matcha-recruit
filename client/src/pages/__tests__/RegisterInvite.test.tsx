import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '../../test/utils';
import RegisterInvite from '../RegisterInvite';

const registerBusinessMock = vi.hoisted(() => vi.fn());
const validateInviteMock = vi.hoisted(() => vi.fn());

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    registerBusiness: registerBusinessMock,
  }),
}));

vi.mock('../../api/client', () => ({
  businessInviteApi: {
    validate: validateInviteMock,
  },
}));

async function fillRequiredFields(user: ReturnType<typeof render>['user']) {
  await user.type(screen.getByPlaceholderText('John Doe'), 'Jordan Founder');
  await user.type(screen.getByPlaceholderText('you@example.com'), 'owner@example.com');
  await user.type(screen.getByPlaceholderText('Acme Corp'), 'Acme Corp');
  await user.type(screen.getByPlaceholderText('Min 8 chars'), 'supersecret');
  await user.type(screen.getByPlaceholderText('Repeat'), 'supersecret');
}

describe('RegisterInvite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    registerBusinessMock.mockResolvedValue(undefined);
    validateInviteMock.mockResolvedValue({
      valid: true,
      expires_at: '2026-12-31T00:00:00Z',
      note: null,
    });
  });

  it('requires headcount and submits invite registration with numeric headcount', async () => {
    const { user, container } = render(
      <MemoryRouter initialEntries={['/register/invite/test-token']}>
        <Routes>
          <Route path="/register/invite/:token" element={<RegisterInvite />} />
          <Route path="/app" element={<div>App Home</div>} />
        </Routes>
      </MemoryRouter>,
      { withRouter: false },
    );

    await waitFor(() => expect(validateInviteMock).toHaveBeenCalledWith('test-token'));
    await screen.findByText("You've been invited to join Matcha. Your account will be approved instantly.");

    await fillRequiredFields(user);
    const headcountInput = screen.getByPlaceholderText('25');
    expect(headcountInput).toBeRequired();
    await user.type(headcountInput, '0');
    const form = container.querySelector('form');
    if (!form) throw new Error('Expected invite registration form');
    fireEvent.submit(form);

    expect(await screen.findByText('Please enter a valid headcount (1 or more)')).toBeInTheDocument();
    expect(registerBusinessMock).not.toHaveBeenCalled();

    await user.clear(headcountInput);
    await user.type(headcountInput, '18');
    await user.click(screen.getByRole('button', { name: 'Create Account' }));

    await waitFor(() => expect(registerBusinessMock).toHaveBeenCalledTimes(1));
    expect(registerBusinessMock).toHaveBeenCalledWith(
      expect.objectContaining({
        company_name: 'Acme Corp',
        email: 'owner@example.com',
        headcount: 18,
        invite_token: 'test-token',
        name: 'Jordan Founder',
      }),
    );
  });
});

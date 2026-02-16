import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '../../test/utils';
import Register from '../Register';

const registerBusinessMock = vi.fn();

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    registerBusiness: registerBusinessMock,
  }),
}));

async function fillRequiredFields(user: ReturnType<typeof render>['user']) {
  await user.type(screen.getByPlaceholderText('John Doe'), 'Jordan Founder');
  await user.type(screen.getByPlaceholderText('you@example.com'), 'owner@example.com');
  await user.type(screen.getByPlaceholderText('Acme Corp'), 'Acme Corp');
  await user.type(screen.getByPlaceholderText('Min 8 chars'), 'supersecret');
  await user.type(screen.getByPlaceholderText('Repeat'), 'supersecret');
}

describe('Register', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    registerBusinessMock.mockResolvedValue(undefined);
  });

  it('requires headcount before submission', async () => {
    const { user, container } = render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>,
      { withRouter: false },
    );

    await fillRequiredFields(user);
    const headcountInput = screen.getByPlaceholderText('25');
    expect(headcountInput).toBeRequired();
    await user.type(headcountInput, '0');
    const form = container.querySelector('form');
    if (!form) throw new Error('Expected registration form');
    fireEvent.submit(form);

    expect(await screen.findByText('Please enter a valid headcount (1 or more)')).toBeInTheDocument();
    expect(registerBusinessMock).not.toHaveBeenCalled();
  });

  it('submits headcount as a number', async () => {
    const { user } = render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>,
      { withRouter: false },
    );

    await fillRequiredFields(user);
    await user.type(screen.getByPlaceholderText('25'), '37');
    await user.click(screen.getByRole('button', { name: 'Create Account' }));

    await waitFor(() => expect(registerBusinessMock).toHaveBeenCalledTimes(1));
    expect(registerBusinessMock).toHaveBeenCalledWith(
      expect.objectContaining({
        company_name: 'Acme Corp',
        email: 'owner@example.com',
        headcount: 37,
        name: 'Jordan Founder',
      }),
    );
  });
});

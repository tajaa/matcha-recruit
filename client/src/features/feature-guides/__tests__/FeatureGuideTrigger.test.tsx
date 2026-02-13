import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '../../../test/utils';
import { FeatureGuideTrigger } from '../FeatureGuideTrigger';
import { markGuideSeen } from '../storage';

// Mock useAuth to provide a userId
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'test-user-1', email: 'test@test.com', role: 'client', is_active: true, created_at: '', last_login: null },
    profile: null,
    betaFeatures: {},
    interviewPrepTokens: 0,
    allowedInterviewRoles: [],
    companyFeatures: {},
    onboardingNeeded: {},
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    registerBusiness: vi.fn(),
    registerCandidate: vi.fn(),
    hasRole: vi.fn(),
    hasBetaFeature: vi.fn(),
    hasFeature: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

// Mock framer-motion to avoid matchMedia issues in jsdom
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children, ...props }: any) => {
      const { initial, animate, exit, transition, ...domProps } = props;
      return <div {...domProps}>{children}</div>;
    },
  },
}));

describe('FeatureGuideTrigger', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders NEW chip when unseen', () => {
    render(<FeatureGuideTrigger guideId="compliance" />);
    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it('always renders Show Me button', () => {
    render(<FeatureGuideTrigger guideId="compliance" />);
    expect(screen.getByText('Show Me')).toBeInTheDocument();
  });

  it('Show Me button visible even after guide is seen', () => {
    markGuideSeen('compliance', 'test-user-1');
    render(<FeatureGuideTrigger guideId="compliance" />);
    expect(screen.getByText('Show Me')).toBeInTheDocument();
  });

  it('hides NEW chip when guide has been seen', () => {
    markGuideSeen('compliance', 'test-user-1');
    render(<FeatureGuideTrigger guideId="compliance" />);
    expect(screen.queryByText('New')).not.toBeInTheDocument();
  });

  it('activates walkthrough when Show Me is clicked', async () => {
    const { user } = render(<FeatureGuideTrigger guideId="compliance" />);
    await user.click(screen.getByText('Show Me'));
    // The walkthrough overlay renders the first step title
    expect(screen.getByText('Locations Sidebar')).toBeInTheDocument();
  });

  it('activates walkthrough when NEW chip is clicked', async () => {
    const { user } = render(<FeatureGuideTrigger guideId="compliance" />);
    await user.click(screen.getByText('New'));
    expect(screen.getByText('Locations Sidebar')).toBeInTheDocument();
  });

  it('hides NEW chip after starting walkthrough', async () => {
    const { user } = render(<FeatureGuideTrigger guideId="compliance" />);
    expect(screen.getByText('New')).toBeInTheDocument();

    await user.click(screen.getByText('Show Me'));
    // After clicking, NEW should be gone (guide marked as seen)
    expect(screen.queryByText('New')).not.toBeInTheDocument();
  });
});

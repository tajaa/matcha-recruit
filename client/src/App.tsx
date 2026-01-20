import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider, ChatAuthProvider } from './context';
import { Layout, ProtectedRoute } from './components';

// Static imports for critical path (landing + auth)
import { Landing } from './pages/Landing';
import { GumFitLanding } from './pages/GumFitLanding';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Unauthorized } from './pages/Unauthorized';
import { ForCandidates } from './pages/ForCandidates';
import { WorkWithUs } from './pages/WorkWithUs';
import { ResumeOnboarding } from './pages/ResumeOnboarding';
import { OutreachLanding } from './pages/OutreachLanding';
import { OutreachScreening } from './pages/OutreachScreening';
import { ScreeningLanding } from './pages/ScreeningLanding';

// Lazy load all other pages
const Interview = lazy(() => import('./pages/Interview'));
const InterviewAnalysis = lazy(() => import('./pages/InterviewAnalysis'));
const Settings = lazy(() => import('./pages/Settings'));
const Tutor = lazy(() => import('./pages/Tutor'));
const TutorMetrics = lazy(() => import('./pages/TutorMetrics'));
const TutorSessionDetail = lazy(() => import('./pages/TutorSessionDetail'));
const ERCopilot = lazy(() => import('./pages/ERCopilot'));
const ERCaseDetail = lazy(() => import('./pages/ERCaseDetail'));
const OfferLetters = lazy(() => import('./pages/OfferLetters'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Policies = lazy(() => import('./pages/Policies'));
const PolicyDetail = lazy(() => import('./pages/PolicyDetail'));
const PolicyForm = lazy(() => import('./pages/PolicyForm'));
const PolicySign = lazy(() => import('./pages/PolicySign'));
const Compliance = lazy(() => import('./pages/Compliance'));
const IRDashboard = lazy(() => import('./pages/IRDashboard'));
const IRList = lazy(() => import('./pages/IRList'));
const IRCreate = lazy(() => import('./pages/IRCreate'));
const IRDetail = lazy(() => import('./pages/IRDetail'));
const InterviewPrepAdmin = lazy(() => import('./pages/InterviewPrepAdmin'));
const PublicJobs = lazy(() => import('./pages/PublicJobs'));
const PublicJobDetail = lazy(() => import('./pages/PublicJobDetail'));
const PublicJobApply = lazy(() => import('./pages/PublicJobApply'));
const PublicBlogList = lazy(() => import('./pages/PublicBlogList'));
const PublicBlogDetail = lazy(() => import('./pages/PublicBlogDetail'));
const BlogAdmin = lazy(() => import('./pages/BlogAdmin'));
const BlogEditor = lazy(() => import('./pages/BlogEditor'));
const BlogCommentsAdmin = lazy(() => import('./pages/BlogCommentsAdmin'));
const TestBot = lazy(() => import('./pages/TestBot').then(m => ({ default: m.TestBot })));

// Employee Management (Admin)
const Employees = lazy(() => import('./pages/Employees'));
const EmployeeDetail = lazy(() => import('./pages/EmployeeDetail'));
const OnboardingTemplates = lazy(() => import('./pages/OnboardingTemplates'));
const PTOManagement = lazy(() => import('./pages/PTOManagement'));
const AcceptInvitation = lazy(() => import('./pages/AcceptInvitation'));

// Employee Portal Pages
const PortalHome = lazy(() => import('./pages/portal/PortalHome'));
const PortalDocuments = lazy(() => import('./pages/portal/PortalDocuments'));
const PortalPTO = lazy(() => import('./pages/portal/PortalPTO'));
const PortalPolicies = lazy(() => import('./pages/portal/PortalPolicies'));
const PortalProfile = lazy(() => import('./pages/portal/PortalProfile'));
const PortalOnboarding = lazy(() => import('./pages/portal/PortalOnboarding'));

// Chat Pages (separate auth system)
const ChatLogin = lazy(() => import('./pages/chat/ChatLogin'));
const ChatRegister = lazy(() => import('./pages/chat/ChatRegister'));
const ChatLayout = lazy(() => import('./pages/chat/ChatLayout'));
const ChatLobby = lazy(() => import('./pages/chat/ChatLobby'));
const ChatRoom = lazy(() => import('./pages/chat/ChatRoom'));

// Creator Pages
const CreatorDashboard = lazy(() => import('./pages/creator/CreatorDashboard'));
const RevenueDashboard = lazy(() => import('./pages/creator/RevenueDashboard'));
const ExpenseTracker = lazy(() => import('./pages/creator/ExpenseTracker'));
const PlatformConnections = lazy(() => import('./pages/creator/PlatformConnections'));
const DealMarketplace = lazy(() => import('./pages/creator/DealMarketplace'));
const MyApplications = lazy(() => import('./pages/creator/MyApplications'));
const MyContracts = lazy(() => import('./pages/creator/MyContracts'));
const CampaignOffers = lazy(() => import('./pages/creator/CampaignOffers').then(m => ({ default: m.CampaignOffers })));
const OfferDetail = lazy(() => import('./pages/creator/CampaignOffers').then(m => ({ default: m.OfferDetail })));
const AffiliateDashboard = lazy(() => import('./pages/creator/AffiliateDashboard'));

// Agency Pages
const AgencyDashboard = lazy(() => import('./pages/agency/AgencyDashboard'));
const DealManager = lazy(() => import('./pages/agency/DealManager'));
const CampaignManager = lazy(() => import('./pages/agency/CampaignManager'));
const CampaignDetail = lazy(() => import('./pages/agency/CampaignDetail'));
const CreatorDiscovery = lazy(() => import('./pages/agency/CreatorDiscovery'));
const CreatorProfile = lazy(() => import('./pages/agency/CreatorProfile'));
const ApplicationReview = lazy(() => import('./pages/agency/ApplicationReview'));
const ContractManager = lazy(() => import('./pages/agency/ContractManager'));

// GumFit Admin Pages
const GumFitDashboard = lazy(() => import('./pages/gumfit/GumFitDashboard'));
const GumFitCreators = lazy(() => import('./pages/gumfit/GumFitCreators'));
const GumFitAgencies = lazy(() => import('./pages/gumfit/GumFitAgencies'));
const GumFitUsers = lazy(() => import('./pages/gumfit/GumFitUsers'));
const GumFitInvites = lazy(() => import('./pages/gumfit/GumFitInvites'));

// Loading fallback
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="flex flex-col items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
        <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
      </div>
    </div>
  );
}

// Redirect component that properly handles the :id parameter
function CompanyRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/app/companies/${id}`} replace />;
}

function App() {
  return (
    <AuthProvider>
      <ChatAuthProvider>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<Landing />} />
              <Route path="/gumfit-landing" element={<GumFitLanding />} />
              <Route path="/for-candidates" element={<ForCandidates />} />
              <Route path="/work-with-us" element={<WorkWithUs />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/onboarding/resume" element={<ResumeOnboarding />} />
              <Route path="/unauthorized" element={<Unauthorized />} />

              {/* Chat routes (separate auth system) */}
              <Route path="/chat/login" element={<ChatLogin />} />
              <Route path="/chat/register" element={<ChatRegister />} />
              <Route path="/chat" element={<ChatLayout />}>
                <Route index element={<ChatLobby />} />
                <Route path=":slug" element={<ChatRoom />} />
              </Route>

            {/* Public Blog */}
            <Route path="/blog" element={<PublicBlogList />} />
            <Route path="/blog/:slug" element={<PublicBlogDetail />} />

            {/* Public outreach routes (token-based access) */}
            <Route path="/outreach/:token" element={<OutreachLanding />} />
            <Route path="/outreach/:token/screening" element={<OutreachScreening />} />

            {/* Admin Shortcuts */}
            <Route path="/admin/blogs/drafts" element={<Navigate to="/app/blog?status=draft" replace />} />

            {/* Direct screening invite (handles auth internally) */}
            <Route path="/screening/:token" element={<ScreeningLanding />} />

            {/* Employee invitation acceptance (public) */}
            <Route path="/invite/:token" element={<AcceptInvitation />} />

            {/* Policy signature (public, token-based) */}
            <Route path="/sign/:token" element={<PolicySign />} />

            {/* Public job board */}
            <Route path="/careers" element={<PublicJobs />} />
            <Route path="/careers/:jobId" element={<PublicJobDetail />} />
            <Route path="/careers/:jobId/apply" element={<PublicJobApply />} />

            {/* Redirects for old routes */}
            <Route path="/companies/:id" element={<CompanyRedirect />} />
            <Route path="/companies" element={<Navigate to="/app" replace />} />

            {/* Interview route (needs auth but outside layout) */}
            <Route
              path="/interview/:id"
              element={
                <ProtectedRoute>
                  <Interview />
                </ProtectedRoute>
              }
            />

            {/* Protected routes with Layout */}
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route
                index
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />

              <Route
                path="offer-letters"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <OfferLetters />
                  </ProtectedRoute>
                }
              />
              <Route
                path="policies"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <Policies />
                  </ProtectedRoute>
                }
              />
              <Route
                path="policies/new"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <PolicyForm />
                  </ProtectedRoute>
                }
              />
              <Route
                path="policies/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <PolicyDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="compliance"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <Compliance />
                  </ProtectedRoute>
                }
              />
              <Route
                path="employees"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <Employees />
                  </ProtectedRoute>
                }
              />
              <Route
                path="employees/:employeeId"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <EmployeeDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="onboarding-templates"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <OnboardingTemplates />
                  </ProtectedRoute>
                }
              />
              <Route
                path="pto"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <PTOManagement />
                  </ProtectedRoute>
                }
              />
              <Route
                path="blog"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogAdmin />
                  </ProtectedRoute>
                }
              />
              <Route
                path="blog/new"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogEditor />
                  </ProtectedRoute>
                }
              />
              <Route
                path="blog/:slug"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogEditor />
                  </ProtectedRoute>
                }
              />
              <Route
                path="blog/comments"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogCommentsAdmin />
                  </ProtectedRoute>
                }
              />






              <Route
                path="test-bot"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <TestBot />
                  </ProtectedRoute>
                }
              />
              <Route
                path="tutor"
                element={
                  <ProtectedRoute roles={['admin', 'candidate']}>
                    <Tutor />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/interview-prep"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <InterviewPrepAdmin />
                  </ProtectedRoute>
                }
              />

              <Route
                path="tutor-metrics"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <TutorMetrics />
                  </ProtectedRoute>
                }
              />
              <Route
                path="tutor-metrics/:id"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <TutorSessionDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="er-copilot"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <ERCopilot />
                  </ProtectedRoute>
                }
              />
              <Route
                path="er-copilot/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <ERCaseDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <IRDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <IRList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/new"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <IRCreate />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <IRDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="analysis/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <InterviewAnalysis />
                  </ProtectedRoute>
                }
              />
              <Route
                path="settings"
                element={
                  <ProtectedRoute>
                    <Settings />
                  </ProtectedRoute>
                }
              />

              {/* Employee Portal Routes */}
              <Route
                path="portal"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalHome />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/documents"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalDocuments />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/pto"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalPTO />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/policies"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalPolicies />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/profile"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalProfile />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/onboarding"
                element={
                  <ProtectedRoute roles={['employee']}>
                    <PortalOnboarding />
                  </ProtectedRoute>
                }
              />

              {/* Creator Routes */}
              <Route
                path="creator"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <CreatorDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/revenue"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <RevenueDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/expenses"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <ExpenseTracker />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/platforms"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <PlatformConnections />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/deals"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <DealMarketplace />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/applications"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <MyApplications />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/contracts"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <MyContracts />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/offers"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <CampaignOffers />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/offers/:offerId"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <OfferDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="creator/affiliate"
                element={
                  <ProtectedRoute roles={['creator']}>
                    <AffiliateDashboard />
                  </ProtectedRoute>
                }
              />

              {/* Agency Routes */}
              <Route
                path="agency"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <AgencyDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/deals"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <DealManager />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/campaigns"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <CampaignManager />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/campaigns/:campaignId"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <CampaignDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/creators"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <CreatorDiscovery />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/creators/:creatorId"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <CreatorProfile />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/applications"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <ApplicationReview />
                  </ProtectedRoute>
                }
              />
              <Route
                path="agency/contracts"
                element={
                  <ProtectedRoute roles={['agency']}>
                    <ContractManager />
                  </ProtectedRoute>
                }
              />

              {/* GumFit Admin Routes */}
              <Route
                path="gumfit"
                element={
                  <ProtectedRoute roles={['gumfit_admin']}>
                    <GumFitDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="gumfit/creators"
                element={
                  <ProtectedRoute roles={['gumfit_admin']}>
                    <GumFitCreators />
                  </ProtectedRoute>
                }
              />
              <Route
                path="gumfit/agencies"
                element={
                  <ProtectedRoute roles={['gumfit_admin']}>
                    <GumFitAgencies />
                  </ProtectedRoute>
                }
              />
              <Route
                path="gumfit/users"
                element={
                  <ProtectedRoute roles={['gumfit_admin']}>
                    <GumFitUsers />
                  </ProtectedRoute>
                }
              />
              <Route
                path="gumfit/invites"
                element={
                  <ProtectedRoute roles={['gumfit_admin']}>
                    <GumFitInvites />
                  </ProtectedRoute>
                }
              />

            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
      </ChatAuthProvider>
    </AuthProvider>
  );
}

export default App;

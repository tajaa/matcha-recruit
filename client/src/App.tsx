import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider, ChatAuthProvider } from './context';
import { Layout, ProtectedRoute } from './components';

// Static imports for critical path (landing + auth)
import { Landing } from './pages/Landing';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
const RegisterInvite = lazy(() => import('./pages/RegisterInvite'));
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
const Handbooks = lazy(() => import('./pages/Handbooks'));
const PolicyDetail = lazy(() => import('./pages/PolicyDetail'));
const PolicyForm = lazy(() => import('./pages/PolicyForm'));
const HandbookDetail = lazy(() => import('./pages/HandbookDetail'));
const HandbookForm = lazy(() => import('./pages/HandbookForm'));
const PolicySign = lazy(() => import('./pages/PolicySign'));
const Compliance = lazy(() => import('./pages/Compliance'));
const GoogleWorkspaceProvisioning = lazy(() => import('./pages/GoogleWorkspaceProvisioning'));
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
const AdminOverview = lazy(() => import('./pages/admin/AdminOverview'));
const BusinessRegistrations = lazy(() => import('./pages/admin/BusinessRegistrations'));
const CompanyFeatures = lazy(() => import('./pages/admin/CompanyFeatures'));
const Jurisdictions = lazy(() => import('./pages/admin/Jurisdictions'));
const PosterOrders = lazy(() => import('./pages/admin/PosterOrders'));
const HRNews = lazy(() => import('./pages/admin/HRNews'));
const CompanyDetail = lazy(() => import('./pages/CompanyDetail'));
const CompanyProfile = lazy(() => import('./pages/CompanyProfile'));
const BulkImport = lazy(() => import('./pages/BulkImport'));

// Employee Management (Admin)
const Employees = lazy(() => import('./pages/Employees'));
const EmployeeDetail = lazy(() => import('./pages/EmployeeDetail'));
const OnboardingTemplates = lazy(() => import('./pages/OnboardingTemplates'));
const PTOManagement = lazy(() => import('./pages/PTOManagement'));
const LeaveManagement = lazy(() => import('./pages/LeaveManagement'));
const Accommodations = lazy(() => import('./pages/Accommodations'));
const AcceptInvitation = lazy(() => import('./pages/AcceptInvitation'));

// Employee Portal Pages
const PortalHome = lazy(() => import('./pages/portal/PortalHome'));
const PortalDocuments = lazy(() => import('./pages/portal/PortalDocuments'));
const PortalPTO = lazy(() => import('./pages/portal/PortalPTO'));
const PortalLeave = lazy(() => import('./pages/portal/PortalLeave'));
const PortalPolicies = lazy(() => import('./pages/portal/PortalPolicies'));
const PortalProfile = lazy(() => import('./pages/portal/PortalProfile'));
const PortalOnboarding = lazy(() => import('./pages/portal/PortalOnboarding'));
const PortalVibeCheck = lazy(() => import('./pages/portal/PortalVibeCheck'));
const PortalENPS = lazy(() => import('./pages/portal/PortalENPS'));
const PortalReviews = lazy(() => import('./pages/portal/PortalReviews'));
const BrokerClients = lazy(() => import('./pages/broker/BrokerClients'));
const BrokerReporting = lazy(() => import('./pages/broker/BrokerReporting'));

// Chat Pages (separate auth system)
const ChatLogin = lazy(() => import('./pages/chat/ChatLogin'));
const ChatRegister = lazy(() => import('./pages/chat/ChatRegister'));
const ChatLayout = lazy(() => import('./pages/chat/ChatLayout'));
const ChatLobby = lazy(() => import('./pages/chat/ChatLobby'));
const ChatRoom = lazy(() => import('./pages/chat/ChatRoom'));

// AI Chat
const AIChat = lazy(() => import('./pages/AIChat'));

// Employee Experience (XP) Pages
const XPDashboard = lazy(() => import('./pages/xp/Dashboard'));
const VibeChecks = lazy(() => import('./pages/xp/VibeChecks'));
const ENPS = lazy(() => import('./pages/xp/ENPS'));
const PerformanceReviews = lazy(() => import('./pages/xp/Reviews'));

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

function LeaveRequestRedirect() {
  const { leaveId } = useParams<{ leaveId: string }>();
  const query = leaveId ? `?leaveId=${encodeURIComponent(leaveId)}` : '';
  return <Navigate to={`/app/matcha/leave${query}`} replace />;
}

function HandbookAliasDetailRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/app/matcha/handbook/${id}`} replace />;
}

function HandbookAliasEditRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/app/matcha/handbook/${id}/edit`} replace />;
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
              <Route path="/for-candidates" element={<ForCandidates />} />
              <Route path="/work-with-us" element={<WorkWithUs />} />
              <Route path="/login" element={<Login />} />
              <Route path="/login/:brokerSlug" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/register/invite/:token" element={<RegisterInvite />} />
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
            <Route path="/admin/blogs/drafts" element={<Navigate to="/app/admin/blog?status=draft" replace />} />

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
            <Route path="/offer-letter" element={<Navigate to="/app/matcha/offer-letters" replace />} />

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

              {/* Company Profile (business admin) */}
              <Route
                path="matcha/company"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <CompanyProfile />
                  </ProtectedRoute>
                }
              />

              {/* HR Routes */}
              <Route
                path="matcha/offer-letters"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="offer_letters">
                    <OfferLetters />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/policies"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="policies">
                    <Policies />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/handbook"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="handbooks">
                    <Handbooks />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/handbook/new"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="handbooks">
                    <HandbookForm />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/handbook/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="handbooks">
                    <HandbookDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/handbook/:id/edit"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="handbooks">
                    <HandbookForm />
                  </ProtectedRoute>
                }
              />
              {/* Legacy alias */}
              <Route path="matcha/hand-book" element={<Navigate to="/app/matcha/handbook" replace />} />
              <Route path="matcha/hand-book/new" element={<Navigate to="/app/matcha/handbook/new" replace />} />
              <Route path="matcha/hand-book/:id" element={<HandbookAliasDetailRedirect />} />
              <Route path="matcha/hand-book/:id/edit" element={<HandbookAliasEditRedirect />} />
              <Route
                path="matcha/policies/new"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="policies">
                    <PolicyForm />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/policies/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="policies">
                    <PolicyDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/policies/:id/edit"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="policies">
                    <PolicyForm />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/compliance"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="compliance">
                    <Compliance />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/employees"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="employees">
                    <Employees />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/setup"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <Navigate to="/app/matcha/company" replace />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/google-workspace"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <GoogleWorkspaceProvisioning />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/employees/:employeeId"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="employees">
                    <EmployeeDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/onboarding-templates"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="employees">
                    <OnboardingTemplates />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/pto"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="time_off">
                    <PTOManagement />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/leave"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="time_off">
                    <LeaveManagement />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/employees/leave/requests/:leaveId"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="time_off">
                    <LeaveRequestRedirect />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/accommodations"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="accommodations">
                    <Accommodations />
                  </ProtectedRoute>
                }
              />

              {/* AI Chat */}
              <Route
                path="ai-chat"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <AIChat />
                  </ProtectedRoute>
                }
              />

              {/* Employee Experience (XP) Routes */}
              <Route
                path="xp/dashboard"
                element={
                  <ProtectedRoute roles={['admin', 'client']} anyRequiredFeature={['vibe_checks', 'enps', 'performance_reviews']}>
                    <XPDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="xp/vibe-checks"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="vibe_checks">
                    <VibeChecks />
                  </ProtectedRoute>
                }
              />
              <Route
                path="xp/enps"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="enps">
                    <ENPS />
                  </ProtectedRoute>
                }
              />
              <Route
                path="xp/reviews"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="performance_reviews">
                    <PerformanceReviews />
                  </ProtectedRoute>
                }
              />

              <Route
                path="matcha/er-copilot"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="er_copilot">
                    <ERCopilot />
                  </ProtectedRoute>
                }
              />
              <Route
                path="matcha/er-copilot/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="er_copilot">
                    <ERCaseDetail />
                  </ProtectedRoute>
                }
              />

              {/* Admin Routes */}
              <Route
                path="admin/overview"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <AdminOverview />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/blog"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogAdmin />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/blog/new"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogEditor />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/blog/:slug"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogEditor />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/blog/comments"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BlogCommentsAdmin />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/test-bot"
                element={
                  <ProtectedRoute roles={['admin', 'client']}>
                    <TestBot />
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
                path="admin/business-registrations"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BusinessRegistrations />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/company-features"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <CompanyFeatures />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/jurisdictions"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <Jurisdictions />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/poster-orders"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <PosterOrders />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/news"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <HRNews />
                  </ProtectedRoute>
                }
              />
              <Route
                path="companies/:id"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <CompanyDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/tutor-metrics"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <TutorMetrics />
                  </ProtectedRoute>
                }
              />
              <Route
                path="admin/tutor-metrics/:id"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <TutorSessionDetail />
                  </ProtectedRoute>
                }
              />



              <Route
                path="import"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <BulkImport />
                  </ProtectedRoute>
                }
              />

              {/* Interview Prep Routes */}
              <Route
                path="tutor"
                element={
                  <ProtectedRoute roles={['admin', 'client', 'candidate']}>
                    <Tutor />
                  </ProtectedRoute>
                }
              />

              {/* Incident Response Routes */}
              <Route
                path="ir"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="incidents">
                    <IRList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/dashboard"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="incidents">
                    <IRDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="incidents">
                    <IRList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/new"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="incidents">
                    <IRCreate />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/:id"
                element={
                  <ProtectedRoute roles={['admin', 'client']} requiredFeature="incidents">
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
              <Route
                path="broker/clients"
                element={
                  <ProtectedRoute roles={['broker']}>
                    <BrokerClients />
                  </ProtectedRoute>
                }
              />
              <Route
                path="broker/reporting"
                element={
                  <ProtectedRoute roles={['broker']}>
                    <BrokerReporting />
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
                  <ProtectedRoute roles={['employee']} requiredFeature="time_off">
                    <PortalPTO />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/leave"
                element={
                  <ProtectedRoute roles={['employee']} requiredFeature="time_off">
                    <PortalLeave />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/policies"
                element={
                  <ProtectedRoute roles={['employee']} requiredFeature="policies">
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
              <Route
                path="portal/vibe-check"
                element={
                  <ProtectedRoute roles={['employee']} requiredFeature="vibe_checks">
                    <PortalVibeCheck />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/enps"
                element={
                  <ProtectedRoute roles={['employee']} requiredFeature="enps">
                    <PortalENPS />
                  </ProtectedRoute>
                }
              />
              <Route
                path="portal/reviews"
                element={
                  <ProtectedRoute roles={['employee']} requiredFeature="performance_reviews">
                    <PortalReviews />
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

import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider } from './context';
import { Layout, ProtectedRoute } from './components';

// Static imports for critical path (landing + auth)
import { Landing } from './pages/Landing';
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
const Policies = lazy(() => import('./pages/Policies'));
const PolicyDetail = lazy(() => import('./pages/PolicyDetail'));
const PolicyForm = lazy(() => import('./pages/PolicyForm'));
const IRDashboard = lazy(() => import('./pages/IRDashboard'));
const IRList = lazy(() => import('./pages/IRList'));
const IRCreate = lazy(() => import('./pages/IRCreate'));
const IRDetail = lazy(() => import('./pages/IRDetail'));
const InterviewPrepAdmin = lazy(() => import('./pages/InterviewPrepAdmin'));
const PublicJobs = lazy(() => import('./pages/PublicJobs'));
const PublicJobDetail = lazy(() => import('./pages/PublicJobDetail'));
const PublicJobApply = lazy(() => import('./pages/PublicJobApply'));

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
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<Landing />} />
            <Route path="/for-candidates" element={<ForCandidates />} />
            <Route path="/work-with-us" element={<WorkWithUs />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/onboarding/resume" element={<ResumeOnboarding />} />
            <Route path="/unauthorized" element={<Unauthorized />} />

            {/* Public outreach routes (token-based access) */}
            <Route path="/outreach/:token" element={<OutreachLanding />} />
            <Route path="/outreach/:token/screening" element={<OutreachScreening />} />

            {/* Direct screening invite (handles auth internally) */}
            <Route path="/screening/:token" element={<ScreeningLanding />} />

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
                    <OfferLetters />
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
                  <ProtectedRoute roles={['admin']}>
                    <ERCopilot />
                  </ProtectedRoute>
                }
              />
              <Route
                path="er-copilot/:id"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <ERCaseDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <IRDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <IRList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/new"
                element={
                  <ProtectedRoute roles={['admin']}>
                    <IRCreate />
                  </ProtectedRoute>
                }
              />
              <Route
                path="ir/incidents/:id"
                element={
                  <ProtectedRoute roles={['admin']}>
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

            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

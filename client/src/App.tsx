import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider } from './context';
import { Layout, ProtectedRoute } from './components';
import {
  Companies,
  CompanyDetail,
  Interview,
  InterviewAnalysis,
  Landing,
  Candidates,
  Positions,
  PositionDetail,
  BulkImport,
  JobSearch,
  TestBot,
  Login,
  Register,
  Unauthorized,
  Settings,
  Careers,
  Openings,
  ForCandidates,
  WorkWithUs,
  Projects,
  ProjectDetail,
  OutreachLanding,
  OutreachScreening,
  ScreeningLanding,
  PublicJobs,
  PublicJobDetail,
  PublicJobApply,
  JobBoards,
  ResumeOnboarding,
  Tutor,
  TutorMetrics,
  TutorSessionDetail,
  ERCopilot,
  ERCaseDetail,
} from './pages';

// Redirect component that properly handles the :id parameter
function CompanyRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/app/companies/${id}`} replace />;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
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
                  <Companies />
                </ProtectedRoute>
              }
            />
            <Route
              path="companies/:id"
              element={
                <ProtectedRoute roles={['admin', 'client']}>
                  <CompanyDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="candidates"
              element={
                <ProtectedRoute roles={['admin', 'client']}>
                  <Candidates />
                </ProtectedRoute>
              }
            />
            <Route
              path="positions"
              element={
                <ProtectedRoute roles={['admin', 'client', 'candidate']}>
                  <Positions />
                </ProtectedRoute>
              }
            />
            <Route
              path="positions/:id"
              element={
                <ProtectedRoute roles={['admin', 'client', 'candidate']}>
                  <PositionDetail />
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
            <Route
              path="jobs"
              element={
                <ProtectedRoute roles={['admin', 'candidate']}>
                  <JobSearch />
                </ProtectedRoute>
              }
            />
            <Route
              path="openings"
              element={
                <ProtectedRoute roles={['admin', 'client']}>
                  <Openings />
                </ProtectedRoute>
              }
            />
            <Route
              path="job-boards"
              element={
                <ProtectedRoute roles={['admin', 'client']}>
                  <JobBoards />
                </ProtectedRoute>
              }
            />
            <Route
              path="projects"
              element={
                <ProtectedRoute roles={['admin']}>
                  <Projects />
                </ProtectedRoute>
              }
            />
            <Route
              path="projects/:id"
              element={
                <ProtectedRoute roles={['admin']}>
                  <ProjectDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="test-bot"
              element={
                <ProtectedRoute roles={['admin', 'candidate']}>
                  <TestBot />
                </ProtectedRoute>
              }
            />
            <Route
              path="test-bot/analysis/:id"
              element={
                <ProtectedRoute roles={['admin', 'candidate']}>
                  <InterviewAnalysis />
                </ProtectedRoute>
              }
            />
            <Route
              path="tutor"
              element={
                <ProtectedRoute roles={['admin']}>
                  <Tutor />
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
              path="careers"
              element={
                <ProtectedRoute>
                  <Careers />
                </ProtectedRoute>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

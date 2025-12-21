import { BrowserRouter, Routes, Route } from 'react-router-dom';
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
} from './pages';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/unauthorized" element={<Unauthorized />} />

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
                <ProtectedRoute roles={['candidate']}>
                  <JobSearch />
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
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

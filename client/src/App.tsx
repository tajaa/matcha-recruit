import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components';
import {
  Companies,
  CompanyDetail,
  Interview,
  Candidates,
  Positions,
  PositionDetail,
  BulkImport,
  JobSearch,
  TestBot,
} from './pages';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Companies />} />
          <Route path="companies/:id" element={<CompanyDetail />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="positions" element={<Positions />} />
          <Route path="positions/:id" element={<PositionDetail />} />
          <Route path="import" element={<BulkImport />} />
          <Route path="jobs" element={<JobSearch />} />
          <Route path="test-bot" element={<TestBot />} />
        </Route>
        <Route path="/interview/:id" element={<Interview />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

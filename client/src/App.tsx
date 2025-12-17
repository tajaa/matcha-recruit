import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components';
import { Companies, CompanyDetail, Interview, Candidates } from './pages';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Companies />} />
          <Route path="companies/:id" element={<CompanyDetail />} />
          <Route path="candidates" element={<Candidates />} />
        </Route>
        <Route path="/interview/:id" element={<Interview />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

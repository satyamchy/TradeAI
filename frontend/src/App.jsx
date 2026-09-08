import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/layout/Navbar.jsx';
import AnalysisPage from './pages/AnalysisPage.jsx';
import TradeLoggingPage from './pages/TradeLoggingPage.jsx';
import JobSchedulerPage from './pages/JobSchedulerPage.jsx';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col" style={{ background: '#060b14' }}>
        <Navbar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/trades" element={<TradeLoggingPage />} />
            <Route path="/jobs" element={<JobSchedulerPage />} />
            <Route path="*" element={<Navigate to="/analysis" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

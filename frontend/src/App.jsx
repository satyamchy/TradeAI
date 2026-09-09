import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar.jsx';
import ConversationPage from './pages/ConversationPage.jsx';
import AnalysisPage from './pages/AnalysisPage.jsx';
import TradeLoggingPage from './pages/TradeLoggingPage.jsx';
import JobSchedulerPage from './pages/JobSchedulerPage.jsx';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col" style={{ background: '#12100E', color: '#F5EBE1' }}>
        <Navbar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/chat" element={<ConversationPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/trades" element={<TradeLoggingPage />} />
            <Route path="/jobs" element={<JobSchedulerPage />} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

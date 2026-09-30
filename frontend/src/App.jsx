import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { session } from './api/stockApi';
import Shell from './components/Shell';
import DeskPage from './pages/DeskPage';
import LoginPage from './pages/LoginPage';
import LogsPage from './pages/LogsPage';
import OrdersPage from './pages/OrdersPage';
import SettingsPage from './pages/SettingsPage';
import UsersPage from './pages/UsersPage';

function Gate() {
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    session().then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) {
    return <div className="boot">Loading</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/desk" replace /> : <LoginPage onLogin={setUser} />} />
      <Route element={user ? <Shell user={user} onLogout={() => setUser(null)} /> : <Navigate to="/login" replace />}>
        <Route path="/desk" element={<DeskPage user={user} />} />
        <Route path="/orders" element={<OrdersPage user={user} />} />
        <Route path="/settings" element={<SettingsPage user={user} onUser={setUser} />} />
        <Route path="/logs" element={<LogsPage user={user} />} />
        <Route path="/users" element={user?.role === 'admin' ? <UsersPage /> : <Navigate to="/desk" replace />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? '/desk' : '/login'} replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Gate />
    </BrowserRouter>
  );
}

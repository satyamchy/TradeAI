import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { logout } from '../api/stockApi';

const links = [
  { to: '/desk', label: 'Desk' },
  { to: '/orders', label: 'Orders' },
  { to: '/settings', label: 'Settings' },
  { to: '/logs', label: 'Logs' },
];

export default function Shell({ user, onLogout }) {
  const navigate = useNavigate();

  async function signOut() {
    await logout();
    onLogout();
    navigate('/login');
  }

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">TradeX</div>
        <nav>
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} className={({ isActive }) => (isActive ? 'nav active' : 'nav')}>
              {link.label}
            </NavLink>
          ))}
          {user.role === 'admin' && (
            <NavLink to="/users" className={({ isActive }) => (isActive ? 'nav active' : 'nav')}>
              Users
            </NavLink>
          )}
        </nav>
        <div className="rail-foot">
          <div className="who">{user.username}</div>
          <div className="role">{user.role}</div>
          <button type="button" className="ghost" onClick={signOut}>Log out</button>
        </div>
      </aside>
      <main className="stage">
        <Outlet />
      </main>
    </div>
  );
}

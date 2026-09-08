import { Navigate } from 'react-router-dom';

function ProtectedRoute({ children }) {
  // The route guard checks only for a token; API interceptors handle expired tokens.
  const token = localStorage.getItem('paios_token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default ProtectedRoute;

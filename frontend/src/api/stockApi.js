import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  withCredentials: true,
});

export function errorText(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || String(item)).join(' ');
  }
  return 'Request failed';
}

export async function login(username, password) {
  const { data } = await client.post('/api/v1/auth/login', { username, password });
  return data.user;
}

export async function logout() {
  await client.post('/api/v1/auth/logout');
}

export async function session() {
  const { data } = await client.get('/api/v1/auth/session');
  return data.user;
}

export async function automationStatus() {
  const { data } = await client.get('/api/v1/automation/status');
  return data;
}

export async function enableAutomation(methods, tradingIndex) {
  const { data } = await client.post('/api/v1/automation/enable', {
    methods,
    trading_index: tradingIndex || undefined,
  });
  return data;
}

export async function disableAutomation() {
  const { data } = await client.post('/api/v1/automation/disable');
  return data;
}

export async function squareOff() {
  const { data } = await client.post('/api/v1/automation/square-off-open-positions');
  return data;
}

export async function funds() {
  const { data } = await client.get('/api/v1/account/funds');
  return data;
}

export async function positions() {
  const { data } = await client.get('/api/v1/account/positions');
  return data;
}

export async function accountOrders() {
  const { data } = await client.get('/api/v1/account/orders');
  return data;
}

export async function closePosition(symbol, productType) {
  const { data } = await client.post('/api/v1/orders/close', {
    symbol,
    product_type: productType,
  });
  return data;
}

export async function cancelOrder(orderId) {
  const { data } = await client.delete(`/api/v1/orders/${orderId}`);
  return data;
}

export async function saveDhanCredentials(clientId, accessToken) {
  const { data } = await client.put('/api/v1/account/dhan-credentials', {
    client_id: clientId,
    access_token: accessToken,
  });
  return data;
}

export async function pendingOrders() {
  const { data } = await client.get('/api/v1/orders/pending');
  return data.orders;
}

export async function requestSuggestion() {
  const { data } = await client.post('/api/v1/suggestions');
  return data;
}

export async function requestDelivery(symbol, side, quantity) {
  const { data } = await client.post('/api/v1/orders/delivery', { symbol, side, quantity });
  return data;
}

export async function placeIntraday(symbol, side, quantity) {
  const { data } = await client.post('/api/v1/orders/intraday', { symbol, side, quantity });
  return data;
}

export async function executePending(id) {
  const { data } = await client.post(`/api/v1/orders/pending/${id}/execute`);
  return data;
}

export async function rejectPending(id) {
  const { data } = await client.post(`/api/v1/orders/pending/${id}/reject`);
  return data;
}

export async function events(userId) {
  const { data } = await client.get('/api/v1/events', {
    params: userId ? { user_id: userId } : {},
  });
  return data.events;
}

export async function users() {
  const { data } = await client.get('/api/v1/users');
  return data.users;
}

export async function createUser(body) {
  const { data } = await client.post('/api/v1/users', body);
  return data;
}

export async function updateUser(id, body) {
  const { data } = await client.patch(`/api/v1/users/${id}`, body);
  return data;
}

export async function automationSettings() {
  const { data } = await client.get('/api/v1/automation/settings');
  return data;
}

export async function patchAutomationSettings(body) {
  const { data } = await client.patch('/api/v1/automation/settings', body);
  return data;
}

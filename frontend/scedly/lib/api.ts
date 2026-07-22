const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export async function apiFetch(path: string, token: string, opts: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...opts.headers },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export function chatStream(message: string, token: string, sessionId = 'web') {
  return fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export { API };

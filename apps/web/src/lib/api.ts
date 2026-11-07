export type ApiError = { error?: { message?: string; code?: string } };

const TOKEN = "aegisops.token";
const USER = "aegisops.user";

export function token(): string | null {
  return sessionStorage.getItem(TOKEN);
}

export function currentUser(): { email: string; display_name: string; roles: string[] } | null {
  const raw = sessionStorage.getItem(USER);
  return raw ? JSON.parse(raw) : null;
}

export function saveSession(accessToken: string, user: object): void {
  sessionStorage.setItem(TOKEN, accessToken);
  sessionStorage.setItem(USER, JSON.stringify(user));
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN);
  sessionStorage.removeItem(USER);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  const bearer = token();
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
  const response = await fetch(path, { ...init, headers });
  const body = (await response.json().catch(() => ({}))) as T & ApiError;
  if (response.status === 401 && path !== "/api/v1/auth/login") {
    clearSession();
    if (location.pathname !== "/login") location.assign("/login");
  }
  if (!response.ok) {
    throw new Error(body.error?.message || `Request failed (${response.status})`);
  }
  return body;
}

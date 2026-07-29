const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH ?? "/api/v1";
let accessToken: string | null = null;
export class ApiRequestError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
  }
}
export function setAccessToken(token: string | null): void { accessToken = token; }
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE_PATH}${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) throw new ApiRequestError(response.status, response.status === 401 ? "인증에 실패했습니다." : "요청을 처리하지 못했습니다.");
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}
export type User = { id: string; username: string; role: "admin" };
export async function login(username: string, password: string): Promise<void> {
  const result = await apiRequest<{access_token: string}>("/auth/login", { method: "POST", body: JSON.stringify({username, password}) });
  setAccessToken(result.access_token);
}
export const getMe = (): Promise<User> => apiRequest<User>("/auth/me");
export async function logout(): Promise<void> { await apiRequest<void>("/auth/logout", {method: "POST"}); setAccessToken(null); }

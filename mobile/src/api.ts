import type {
  Club,
  Fixture,
  Product,
  Receipt,
  Score,
  Session,
  Settings,
  Standing,
  SyncResult,
} from "./types";
import { friendlyError } from "./domain";

// These mobile read/login paths are the integration boundary. Audit writes follow Part I exactly.
export const routes = {
  login: "/api/v1/auth/login",
  fixtures: "/api/v1/fixtures",
  products: "/api/v1/products",
  club: (id: string) => `/api/v1/clubs/${encodeURIComponent(id)}`,
  standings: (id: string) => `/audit/v1/standings/${encodeURIComponent(id)}`,
  score: (id: string) => `/audit/v1/score/${encodeURIComponent(id)}`,
};
export class NetworkError extends Error {}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  server: string,
  path: string,
  token?: string,
  body?: unknown,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  let response: Response;
  try {
    response = await fetch(server + path, {
      method: body === undefined ? "GET" : "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new NetworkError(
      "Cannot reach the team server. Check its address and join the same hotspot.",
    );
  } finally {
    clearTimeout(timer);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      response.status,
      data?.error?.code ?? "UNAVAILABLE",
      response.status === 404
        ? "This server endpoint is not available yet. Check the backend integration."
        : friendlyError(data?.error?.code ?? "UNAVAILABLE"),
    );
  if (data === null)
    throw new ApiError(
      502,
      "INVALID_RESPONSE",
      "The server returned an unreadable response.",
    );
  return data as T;
}
export async function login(
  settings: Settings,
  email: string,
  password: string,
): Promise<Session> {
  const data = await request<Session & { access_token?: string }>(
    settings.server,
    routes.login,
    undefined,
    { email, password },
  );
  const token = data.token ?? data.access_token;
  if (
    !token ||
    !data.user_id ||
    (data.role !== "super_admin" && !data.tenant_id) ||
    ![
      "super_admin",
      "league_organizer",
      "club_manager",
      "player",
      "viewer",
    ].includes(data.role)
  )
    throw new Error(
      "Login response must include token, role, user_id and tenant_id. See mobile/INTEGRATION.md.",
    );
  return { ...data, token, email };
}
export const api = {
  fixtures: (s: Settings, token: string) =>
    request<{ fixtures: Fixture[] }>(s.server, routes.fixtures, token),
  standings: (s: Settings, token: string) =>
    request<{ table: Standing[] }>(s.server, routes.standings(s.league), token),
  club: (s: Settings, token: string) =>
    request<Club>(s.server, routes.club(s.club), token),
  products: (s: Settings, token: string) =>
    request<{ products: Product[] }>(s.server, routes.products, token),
  score: (s: Settings, token: string, id: string) =>
    request<Score>(s.server, routes.score(id), token),
  checkout: (s: Settings, token: string, body: unknown) =>
    request<Receipt>(s.server, "/audit/v1/checkout", token, body),
  sync: (s: Settings, token: string, body: unknown) =>
    request<{ results: SyncResult[] }>(
      s.server,
      "/audit/v1/offline-sync",
      token,
      body,
    ),
};

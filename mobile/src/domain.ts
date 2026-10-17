import type { OfflineAction, QueueItem, SyncResult } from "./types";

export function actionId(prefix = "action") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
export function money(minor: number) {
  return `PKR ${(minor / 100).toFixed(2)}`;
}
export function validServer(raw: string) {
  const url = new URL(raw.trim());
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error(
      "Use an http:// or https:// server address without credentials or query parameters.",
    );
  return url.toString().replace(/\/$/, "");
}
export function syncEnvelope(device_id: string, actions: QueueItem[]) {
  return {
    device_id,
    actions: actions
      .filter((a) => a.state === "pending")
      .slice(0, 100)
      .map(
        ({
          action_id,
          type,
          queued_at,
          base_version,
          payload,
        }): OfflineAction => ({
          action_id,
          type,
          queued_at,
          base_version,
          payload,
        }),
      ),
  };
}
export function applySyncResults(actions: QueueItem[], results: SyncResult[]) {
  const byId = new Map(results.map((r) => [r.action_id, r]));
  return actions.map((a) => {
    const r = byId.get(a.action_id);
    return r
      ? { ...a, state: r.status, reason: r.error_code ?? r.resolution }
      : a;
  });
}
export function friendlyError(code: string) {
  const messages: Record<string, string> = {
    SQUAD_FULL: "The destination squad is full.",
    OUT_OF_STOCK: "This size has sold out. Choose another variant.",
    TRANSFER_WINDOW_CLOSED: "The transfer window is closed.",
    PLAYER_ON_LOAN: "This player is already on loan.",
    MIN_POSITION_VIOLATION:
      "The move would leave the squad without a required position.",
    NOT_IN_SQUAD: "This player is no longer registered in the selected squad.",
    CROSS_TENANT_TRANSFER: "Players cannot move between these organizations.",
    MATCH_NOT_IN_PROGRESS:
      "This match is not in progress. Your scoring action was not applied.",
    INVALID_COMPENSATION:
      "That event cannot be reversed, or has already been reversed.",
    INVALID_BASE_VERSION:
      "The action references a newer version than the server has.",
    DUPLICATE_EVENT_ID:
      "That event identifier was already used for a different action.",
    PAYMENT_DECLINED: "The mock payment was declined. Your cart has been kept.",
    PAYMENT_CAPTURE_FAILED:
      "Payment capture failed. No purchase was completed.",
    FORBIDDEN: "Your account does not have permission for this action.",
    UNAUTHENTICATED: "Sign in again to continue.",
    VALIDATION_ERROR: "Check the entered values and try again.",
    MATCH_NOT_FOUND: "The selected match was not found.",
    PLAYER_NOT_FOUND: "The selected player was not found.",
    SQUAD_NOT_FOUND: "The selected squad was not found.",
  };
  return (
    messages[code] ??
    "The server could not apply this action. Refresh the latest data and try again."
  );
}

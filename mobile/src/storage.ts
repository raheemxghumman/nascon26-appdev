import * as SQLite from "expo-sqlite";
import * as SecureStore from "expo-secure-store";
import type { QueueItem, Session } from "./types";

const database = SQLite.openDatabaseAsync("nascon-mobile.db").then(
  async (db) => {
    await db.execAsync(
      "PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY NOT NULL, scope TEXT NOT NULL, value TEXT NOT NULL);",
    );
    return db;
  },
);
export async function read<T>(key: string): Promise<T | null> {
  const row = await (
    await database
  ).getFirstAsync<{ value: string }>(
    "SELECT value FROM cache WHERE key=?",
    key,
  );
  return row ? (JSON.parse(row.value) as T) : null;
}
export async function write(key: string, value: unknown) {
  await (
    await database
  ).runAsync(
    "INSERT OR REPLACE INTO cache(key,value) VALUES(?,?)",
    key,
    JSON.stringify(value),
  );
}
export async function queue(scope: string) {
  const rows = await (
    await database
  ).getAllAsync<{ value: string }>(
    "SELECT value FROM actions WHERE scope=? ORDER BY rowid",
    scope,
  );
  return rows.map((r) => JSON.parse(r.value) as QueueItem);
}
export async function saveAction(a: QueueItem) {
  await (
    await database
  ).runAsync(
    "INSERT OR REPLACE INTO actions(id,scope,value) VALUES(?,?,?)",
    a.action_id,
    a.scope,
    JSON.stringify(a),
  );
}
export async function clearFinished(scope: string) {
  const actions = await queue(scope);
  for (const a of actions.filter((a) => a.state !== "pending"))
    await (
      await database
    ).runAsync(
      "DELETE FROM actions WHERE id=? AND scope=?",
      a.action_id,
      scope,
    );
}
// SecureStore uses Android Keystore. Tokens never enter SQLite, logs or plain settings.
export async function saveSession(server: string, session: Session | null) {
  if (session)
    await SecureStore.setItemAsync(
      "nascon-session",
      JSON.stringify({ server, session }),
    );
  else await SecureStore.deleteItemAsync("nascon-session");
}
export async function loadSession(): Promise<{
  server: string;
  session: Session;
} | null> {
  const raw = await SecureStore.getItemAsync("nascon-session");
  return raw ? JSON.parse(raw) : null;
}

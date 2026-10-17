import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { OfflineAction, QueueItem, Session, Settings } from "./types";
import * as db from "./storage";
import { api, login as apiLogin, request } from "./api";
import {
  actionId,
  applySyncResults,
  syncEnvelope,
  validServer,
} from "./domain";

type State = {
  ready: boolean;
  settings: Settings;
  session: Session | null;
  preview: boolean;
  online: boolean;
  syncing: boolean;
  actions: QueueItem[];
  error: string;
  setPreview: (value: boolean) => void;
  setError: (value: string) => void;
  configure: (value: Settings) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  enqueue: (
    action: Omit<OfflineAction, "action_id" | "queued_at">,
  ) => Promise<void>;
  sync: () => Promise<void>;
  clearHistory: () => Promise<void>;
  scope: string;
  deviceId: string;
};
const Context = createContext<State | null>(null);
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false),
    [settings, setSettings] = useState<Settings>({
      server: "http://10.0.2.2:8080",
      league: "league-alpha-1",
      club: "club-alpha-1",
    });
  const [session, setSession] = useState<Session | null>(null),
    [preview, setPreview] = useState(false),
    [online, setOnline] = useState(false),
    [syncing, setSyncing] = useState(false),
    [actions, setActions] = useState<QueueItem[]>([]),
    [error, setError] = useState(""),
    [deviceId, setDeviceId] = useState("");
  const busy = useRef(false),
    scope = `${settings.server}|${session?.tenant_id ?? "signed-out"}|${session?.user_id ?? "signed-out"}`;
  const activeScope = useRef(scope);
  activeScope.current = scope;
  useEffect(() => {
    void (async () => {
      try {
        const saved = await db.read<Settings>("settings");
        if (saved) setSettings(saved);
        const credential = await db.loadSession();
        if (
          credential &&
          credential.server === (saved?.server ?? settings.server)
        )
          setSession(credential.session);
        let device = await db.read<string>("device");
        if (!device) {
          device = actionId("device");
          await db.write("device", device);
        }
        setDeviceId(device);
      } catch (e) {
        setError(String(e));
      } finally {
        setReady(true);
      }
    })(); /* Initial restoration only. */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    setActions([]);
    void db
      .queue(scope)
      .then((value) => {
        if (activeScope.current === scope) setActions(value);
      })
      .catch((e) => setError(String(e)));
  }, [scope]);
  const sync = useCallback(async () => {
    if (!session || preview || busy.current) return;
    busy.current = true;
    setSyncing(true);
    try {
      const saved = await db.queue(scope),
        body = syncEnvelope(deviceId, saved);
      if (!body.actions.length) return;
      const response = await api.sync(settings, session.token, body);
      const submitted = new Set(body.actions.map((a) => a.action_id));
      if (
        !Array.isArray(response.results) ||
        response.results.length !== submitted.size ||
        new Set(response.results.map((r) => r.action_id)).size !==
          submitted.size ||
        response.results.some(
          (r) =>
            !submitted.has(r.action_id) ||
            !["applied", "rejected", "duplicate"].includes(r.status),
        )
      )
        throw new Error(
          "The server returned incomplete sync results. Pending actions have been preserved.",
        );
      const resolved = applySyncResults(saved, response.results);
      for (const a of resolved) await db.saveAction(a);
      const refreshed = await db.queue(scope);
      if (activeScope.current === scope) {
        setActions(refreshed);
        setOnline(true);
        setError("");
      }
    } catch (e) {
      if (activeScope.current === scope)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      busy.current = false;
      setSyncing(false);
    }
  }, [session, preview, scope, deviceId, settings]);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    const check = async () => {
      try {
        await request(settings.server, "/health");
        if (active) setOnline(true);
      } catch {
        if (active) setOnline(false);
      }
    };
    void check();
    const timer = setInterval(() => void check(), 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [settings.server, ready]);
  useEffect(() => {
    if (online && actions.some((a) => a.state === "pending")) void sync();
  }, [online, actions, sync]);
  const configure = async (value: Settings) => {
    const next = {
      ...value,
      server: validServer(value.server),
      league: value.league.trim(),
      club: value.club.trim(),
    };
    if (!next.league || !next.club)
      throw new Error("Enter a league and club identifier.");
    if (next.server !== settings.server) {
      await db.saveSession(settings.server, null);
      setSession(null);
      setOnline(false);
      setPreview(false);
    }
    await db.write("settings", next);
    setSettings(next);
  };
  const signIn = async (email: string, password: string) => {
    const account = await apiLogin(settings, email.trim(), password);
    await db.saveSession(settings.server, account);
    setSession(account);
    setPreview(false);
    setError("");
    setOnline(true);
  };
  const signOut = async () => {
    await db.saveSession(settings.server, null);
    setSession(null);
    setPreview(false);
  };
  const enqueue = async (
    input: Omit<OfflineAction, "action_id" | "queued_at">,
  ) => {
    if (!session || preview)
      throw new Error("Sign in to queue actions. Preview data is read-only.");
    const allowed =
      input.type === "score_event"
        ? ["super_admin", "league_organizer"]
        : ["super_admin", "club_manager"];
    if (!allowed.includes(session.role))
      throw new Error("Your account cannot perform this action.");
    const action: QueueItem = {
      ...input,
      action_id: actionId(),
      queued_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      scope,
      state: "pending",
    };
    await db.saveAction(action);
    setActions(await db.queue(scope));
  };
  const clearHistory = async () => {
    await db.clearFinished(scope);
    setActions(await db.queue(scope));
  };
  return (
    <Context.Provider
      value={{
        ready,
        settings,
        session,
        preview,
        online,
        syncing,
        actions,
        error,
        setPreview,
        setError,
        configure,
        signIn,
        signOut,
        enqueue,
        sync,
        clearHistory,
        scope,
        deviceId,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useApp() {
  const state = useContext(Context);
  if (!state) throw new Error("AppProvider missing");
  return state;
}

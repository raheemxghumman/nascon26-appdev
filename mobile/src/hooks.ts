import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "./state";
import * as storage from "./storage";

export function useResource<T>(
  name: string,
  loader: () => Promise<T>,
  sample: T,
) {
  const app = useApp(),
    [data, setData] = useState<T | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [cached, setCached] = useState(false);
  const current = useRef(loader);
  current.current = loader;
  const generation = useRef(0),
    sampleRef = useRef(sample);
  sampleRef.current = sample;
  const key = `${app.scope}|${name}`;
  const refresh = useCallback(async () => {
    const run = ++generation.current;
    setError("");
    setLoading(true);
    setData(null);
    setCached(false);
    try {
      if (app.preview) {
        setData(sampleRef.current);
        return;
      }
      const saved = await storage.read<T>(key);
      if (run !== generation.current) return;
      setData(saved);
      setCached(Boolean(saved));
      if (!app.session || !app.online) {
        if (!saved)
          setError("No saved data yet. Connect and refresh this screen first.");
        return;
      }
      const fresh = await current.current();
      if (run !== generation.current) return;
      await storage.write(key, fresh);
      setData(fresh);
      setCached(false);
    } catch (e) {
      if (run === generation.current)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (run === generation.current) setLoading(false);
    }
  }, [key, app.preview, app.online, app.session]);
  useEffect(() => {
    void refresh();
    return () => {
      generation.current++;
    };
  }, [refresh]);
  return { data, loading, error, cached, refresh };
}

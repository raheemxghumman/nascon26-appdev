export function redirectSystemPath({ path }: { path: string; initial: boolean }) {
  try {
    const url = new URL(path, "nascon://app");
    if (["entity", "stream"].includes(url.hostname)) {
      const id = url.pathname.split("/").filter(Boolean)[0];
      if (id && /^[a-zA-Z0-9_.:-]{1,80}$/.test(id))
        return `/${url.hostname}/${encodeURIComponent(id)}`;
    }
    return path;
  } catch {
    return "/";
  }
}

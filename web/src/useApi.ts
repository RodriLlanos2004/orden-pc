import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  return p.toString();
}

/** GET con estado. Al recargar conserva los datos anteriores (sin parpadeo de esqueleto). */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [vuelta, setVuelta] = useState(0);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true);
    setError("");
    api<T>(path)
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [path, vuelta]);
  const recargar = useCallback(() => setVuelta((v) => v + 1), []);
  return { data, error, loading, setData, recargar };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export type ScanSnapshot = {
  status: "inactivo" | "escaneando" | "terminado" | "cancelado" | "error";
  phase: "" | "recorrido" | "proyectos" | "duplicados";
  files: number;
  dirs: number;
  bytes: number;
  hashed: number;
  current: string;
  expected_files: number | null;
  started: number | null;
  finished: number | null;
  error: string | null;
};

export type Summary = { scanned: false } | { scanned: true; finished: number; duration: number; scanned_files: number; scanned_bytes: number };

export function useScan() {
  const [snap, setSnap] = useState<ScanSnapshot | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const source = useRef<EventSource | null>(null);

  const refreshSummary = useCallback(() => {
    api<Summary>("/api/summary").then(setSummary).catch((e: Error) => setError(e.message));
  }, []);

  const listen = useCallback(() => {
    source.current?.close();
    const es = new EventSource("/api/scan/events");
    source.current = es;
    es.onmessage = (e) => {
      const s: ScanSnapshot = JSON.parse(e.data);
      setSnap(s);
      if (s.status !== "escaneando") {
        es.close();
        refreshSummary();
      }
    };
    es.onerror = () => es.close();
  }, [refreshSummary]);

  useEffect(() => {
    refreshSummary();
    api<ScanSnapshot>("/api/scan/status")
      .then((s) => {
        setSnap(s);
        if (s.status === "escaneando") listen();
      })
      .catch((e: Error) => setError(e.message));
    return () => source.current?.close();
  }, [listen, refreshSummary]);

  async function start() {
    setError("");
    try {
      setSnap(await api<ScanSnapshot>("/api/scan", { method: "POST" }));
      listen();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function stop() {
    try {
      await api("/api/scan/stop", { method: "POST" });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return { snap, summary, error, start, stop, scanning: snap?.status === "escaneando" };
}

// Tamaños en base 1024 con la etiqueta "GB", igual que el Explorador de Windows.
const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < UNITS.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toLocaleString("es-MX", { maximumFractionDigits: n < 10 && i > 0 ? 1 : 0 })} ${UNITS[i]}`;
}

export const toGB = (bytes: number) => bytes / 1024 ** 3;
export const fmtInt = (n: number) => Math.round(n).toLocaleString("es-MX");
export const fmtPct = (n: number) => (n > 0 && n < 1 ? "menos de 1 %" : `${Math.round(n)} %`);
export const fmtDuration = (seconds: number) => (seconds < 60 ? `${Math.max(1, Math.round(seconds))} s` : `${Math.round(seconds / 60)} min`);

const dateFmt = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium" });
const dateTimeFmt = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
export const fmtDate = (epochSeconds: number | null) => (epochSeconds ? dateFmt.format(epochSeconds * 1000) : "Sin dato");
export const fmtDateTime = (epochSeconds: number | null) => (epochSeconds ? dateTimeFmt.format(epochSeconds * 1000) : "Sin dato");

const rtf = new Intl.RelativeTimeFormat("es-MX", { numeric: "auto" });

/** `epochSeconds` como "hace 5 minutos", "ayer". */
export function timeAgo(epochSeconds: number): string {
  const diff = epochSeconds - Date.now() / 1000;
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 30],
    ["month", 12],
    ["year", Infinity],
  ];
  let value = diff;
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return rtf.format(Math.round(value), unit);
    value /= size;
  }
  return "";
}

// El servidor inyecta el token en index.html; ninguna otra página puede leerlo.
export const token = document.querySelector<HTMLMetaElement>('meta[name="orden-token"]')?.content ?? "";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Orden-Token": token, ...init.headers },
    });
  } catch {
    throw new Error("Sin conexión con Orden PC. Revisa que la terminal donde lo abriste siga abierta.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `El servidor respondió con el código ${res.status}.`);
  return body as T;
}

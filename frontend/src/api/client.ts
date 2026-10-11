import type {
  CaptureDetail,
  Capture,
  FrameDetail,
  FramePage,
  LiveState,
  ProtocolStatus,
  Source,
  ValidateResult,
} from "./types";

/** Erreur renvoyée par l'API, avec le message français du serveur. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public body: Record<string, unknown>,
  ) {
    super(describe(body) || `Erreur ${status}`);
  }
}

function describe(body: Record<string, unknown>): string {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.errors)) return body.errors.join("\n");
  return Object.entries(body)
    .map(([k, v]) => `${k} : ${Array.isArray(v) ? v.join(", ") : String(v)}`)
    .join("\n");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, init);
  } catch {
    throw new ApiError(0, { detail: "Serveur injoignable. Vérifiez que l'API tourne (make back)." });
  }
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(resp.status, body);
  return body as T;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: data === undefined ? undefined : JSON.stringify(data),
});

export const api = {
  captures: () => request<Capture[]>("/api/captures/"),
  capture: (id: number) => request<CaptureDetail>(`/api/captures/${id}/`),
  deleteCapture: (id: number) => request<void>(`/api/captures/${id}/`, { method: "DELETE" }),
  importCapture: (form: FormData) => request<CaptureDetail>("/api/captures/", { method: "POST", body: form }),

  frames: (params: URLSearchParams) => request<FramePage>(`/api/frames/?${params}`),
  frame: (id: number) => request<FrameDetail>(`/api/frames/${id}/`),

  sources: () => request<Source[]>("/api/sources/"),

  live: () => request<LiveState>("/api/live/"),
  startLive: (name: string) => request<LiveState>("/api/live/start/", json("POST", { name })),
  stopLive: () => request<LiveState>("/api/live/stop/", json("POST")),

  protocols: () => request<ProtocolStatus[]>("/api/protocols/"),
  protocolYaml: (name: string) =>
    request<{ name: string; yaml: string; status: ProtocolStatus | null }>(`/api/protocols/${name}/`),
  saveProtocol: (name: string, yaml: string) => request<{ ok: true }>(`/api/protocols/${name}/`, json("PUT", { yaml })),
  validateProtocol: (yaml: string, hex: string) =>
    request<ValidateResult>("/api/protocols/validate/", json("POST", { yaml, hex })),
};

export function exportUrl(captureId: number, format: "csv" | "log", filters: URLSearchParams, direction?: "in" | "out") {
  const p = new URLSearchParams(filters);
  p.delete("frame");
  p.set("format", format);
  if (direction) p.set("direction", direction);
  return `/api/captures/${captureId}/export/?${p}`;
}

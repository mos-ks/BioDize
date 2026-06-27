// Typed client for the BioDize FastAPI backend.
//
// The base URL is runtime-configurable (so the same static build works against
// the local server, a Cloudflare tunnel, or api.biodize.tech): it reads from
// localStorage first, then VITE_API_BASE, then a baked-in default. Change it at
// runtime with `setApiBase()` (the in-app gear settings) — no rebuild needed.

import type {
  AnnotationInput,
  CorrectionInput,
  Distribution,
  DocumentSummary,
  EvalResult,
  Field,
  FieldFilters,
  Flag,
  Health,
  JobStatus,
  ProcessResult,
} from "./types";

const LS_KEY = "biodize_api_base";

const DEFAULT_API_BASE =
  (import.meta.env.VITE_API_BASE && import.meta.env.VITE_API_BASE.trim()) ||
  "https://counted-attending-stephanie-senate.trycloudflare.com";

function clean(base: string): string {
  return base.trim().replace(/\/+$/, "");
}

export function getApiBase(): string {
  if (typeof localStorage !== "undefined") {
    const saved = localStorage.getItem(LS_KEY);
    if (saved && saved.trim()) return clean(saved);
  }
  return clean(DEFAULT_API_BASE);
}

export function setApiBase(base: string): void {
  if (typeof localStorage === "undefined") return;
  const v = clean(base);
  if (v) localStorage.setItem(LS_KEY, v);
  else localStorage.removeItem(LS_KEY);
}

export function resetApiBase(): void {
  if (typeof localStorage !== "undefined") localStorage.removeItem(LS_KEY);
}

export function defaultApiBase(): string {
  return clean(DEFAULT_API_BASE);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_PREFIX = "/api/v1";

function qs(params: object): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    throw new ApiError(0, `Network error reaching ${getApiBase()} — is the backend up and the URL correct?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body && (body.detail ?? body.message)) || detail;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Endpoints --------------------------------------------------------------

export const api = {
  // health (unprefixed)
  health: () => request<Health>("/health"),

  // documents
  listDocuments: () => request<DocumentSummary[]>(`${API_PREFIX}/documents`),
  getDocument: (id: string) => request<DocumentSummary>(`${API_PREFIX}/documents/${id}`),

  /** Run the full pipeline synchronously (holds the request open). */
  processDocument: (opts: { source_path?: string; max_pages?: number } = {}) =>
    request<ProcessResult>(`${API_PREFIX}/documents/process${qs(opts)}`, { method: "POST" }),

  /** Start the pipeline in the background; returns a job id to poll. Use this for
   *  live runs — it survives long durations and proxy/tunnel request limits. */
  processDocumentAsync: (opts: { source_path?: string; max_pages?: number } = {}) =>
    request<{ job_id: string; status: string }>(
      `${API_PREFIX}/documents/process_async${qs(opts)}`,
      { method: "POST" },
    ),

  /** Poll a background processing job's progress. */
  getJob: (jobId: string) => request<JobStatus>(`${API_PREFIX}/documents/jobs/${jobId}`),

  /** Create the next simulated demo batch (offline, no upload). */
  simulateDocument: () =>
    request<ProcessResult>(`${API_PREFIX}/documents/simulate`, { method: "POST" }),

  /** Delete a batch record and all its data. */
  deleteDocument: (id: string) =>
    request<{ deleted: string }>(`${API_PREFIX}/documents/${id}`, { method: "DELETE" }),

  /** Upload a PDF (multipart). Returns the stored source_path for processing. */
  uploadDocument: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ source_path: string; filename: string; hint: string }>(
      `${API_PREFIX}/documents`,
      { method: "POST", body: fd },
    );
  },

  // fields & review queue
  listFields: (documentId: string, filters: FieldFilters = {}) =>
    request<Field[]>(`${API_PREFIX}/documents/${documentId}/fields${qs(filters)}`),
  getQueue: (documentId: string) =>
    request<Field[]>(`${API_PREFIX}/documents/${documentId}/queue`),
  getField: (fieldId: string) => request<Field>(`${API_PREFIX}/fields/${fieldId}`),

  /** Delete a human-added entry (model fields can't be deleted, only corrected). */
  deleteField: (fieldId: string) =>
    request<{ deleted: string }>(`${API_PREFIX}/fields/${fieldId}`, { method: "DELETE" }),

  // AI evaluation vs ground truth
  getEvaluation: (documentId: string) =>
    request<EvalResult>(`${API_PREFIX}/documents/${documentId}/evaluation`),
  patchField: (fieldId: string, body: CorrectionInput) =>
    request<Field>(`${API_PREFIX}/fields/${fieldId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // flags (dashboard)
  listFlags: (documentId: string, filters: { severity?: string; category?: string } = {}) =>
    request<Flag[]>(`${API_PREFIX}/documents/${documentId}/flags${qs(filters)}`),

  // stats
  getDistribution: (role: string, bins = 10) =>
    request<Distribution>(`${API_PREFIX}/stats/roles/${encodeURIComponent(role)}/distribution${qs({ bins })}`),

  /** Create a human-labeled entry from a box drawn on the PDF. */
  addAnnotation: (documentId: string, body: AnnotationInput) =>
    request<Field>(`${API_PREFIX}/documents/${documentId}/annotations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // direct URLs (for <img> / download)
  pageImageUrl: (documentId: string, pageNo: number) =>
    `${getApiBase()}${API_PREFIX}/documents/${documentId}/pages/${pageNo}/image`,
  exportUrl: (documentId: string) =>
    `${getApiBase()}${API_PREFIX}/documents/${documentId}/export.xlsx`,
  csvUrl: (documentId: string) =>
    `${getApiBase()}${API_PREFIX}/documents/${documentId}/export.csv`,
  changelogUrl: (documentId: string) =>
    `${getApiBase()}${API_PREFIX}/documents/${documentId}/changes.csv`,
};

export type Api = typeof api;

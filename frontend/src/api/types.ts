// API DTOs — mirror the FastAPI backend (app/schemas/schemas.py) exactly.
// Verified against the live /api/v1 responses.

export type Severity = "error" | "warning";

export type FlagCategory =
  | "extraction"
  | "calculation"
  | "range"
  | "temporal"
  | "four_eyes"
  | "format"
  | "applicability"
  | "cross_reference"
  | "deviation"
  | "outlier"
  | "missing";

export type FieldStatus =
  | "extracted"
  | "validated"
  | "auto_accepted"
  | "needs_review"
  | "confirmed"
  | "corrected";

export type DocumentStatus = "uploaded" | "processing" | "processed" | "failed";

export interface Flag {
  id: string;
  severity: Severity;
  category: FlagCategory;
  code: string;
  message: string;
  expected?: string | null;
  actual?: string | null;
}

export interface Read {
  model: string;
  value_raw?: string | null;
  confidence: number;
}

/** Normalized 0..1 box: [x0, y0, x1, y1], origin top-left. */
export type BBox = [number, number, number, number];

export interface Field {
  id: string;
  document_id: string;
  chapter?: string | null;
  block_key?: string | null;
  page_no: number;
  role?: string | null;
  label_raw?: string | null;
  value?: string | null; // normalized value
  value_raw?: string | null;
  value_type?: string | null;
  unit?: string | null;
  nks?: number | null;
  bbox?: BBox | null;
  confidence: number;
  status: FieldStatus;
  reads: Read[];
  flags: Flag[];
}

export interface DocumentSummary {
  id: string;
  doc_no: string;
  title?: string | null;
  status: DocumentStatus;
  page_count: number;
  n_fields: number;
  n_errors: number;
  n_warnings: number;
  n_needs_review: number;
}

export interface ProcessResult {
  document_id: string;
  status: string;
  n_fields: number;
  n_errors: number;
  n_warnings: number;
  n_auto_accepted: number;
  n_needs_review: number;
}

export interface HistogramBin {
  start: number;
  end: number;
  count: number;
}

export interface Distribution {
  role: string;
  n: number;
  mean?: number | null;
  std?: number | null;
  min?: number | null;
  max?: number | null;
  histogram: HistogramBin[];
}

export interface Health {
  status: string;
  extractor: string;
  ocr_engine: string;
  db: string;
}

export interface CorrectionInput {
  value?: string | null;
  action: "confirm" | "correct";
  reason?: string | null;
  actor?: string | null;
}

export interface FieldFilters {
  status?: FieldStatus;
  severity?: Severity;
  category?: FlagCategory;
  page_no?: number;
  role?: string;
}

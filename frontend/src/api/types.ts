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
  | "missing"
  | "human";

export interface AnnotationInput {
  page_no: number;
  bbox?: number[] | null;
  label?: string; // the title
  tag?: string; // short category tag → becomes the flag code chip
  value?: string;
  note?: string;
  severity?: "error" | "warning" | null;
  actor?: string;
}

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
  source?: string; // model | ocr | human (human entries are deletable)
  is_handwritten?: boolean | null; // blue (hand-filled) vs black (printed)
  is_verified?: boolean; // corroborated by calculation or a second identical value
  verified_reason?: string | null;
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
  processing_ms?: number | null; // time the pipeline took to generate this record
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

/** Background processing job (polled while a live run is in progress). */
export interface JobStatus {
  job_id: string;
  status: "processing" | "processed" | "failed";
  stage: string;
  page_done: number;
  page_total: number;
  document_id?: string | null;
  error?: string | null;
  elapsed_ms: number;
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

// --- AI evaluation vs ground truth ------------------------------------------
// All accuracy ratios are 0..1. The four *_acc/coverage fields on the aggregate
// may be null (= "n/a" — nothing of that kind on the gold pages).

export interface EvalAggregate {
  tp: number;
  fp: number;
  fn: number;
  rule_precision: number;
  rule_recall: number;
  rule_f1: number;
  value_acc: number | null;
  checkbox_acc: number | null;
  signature_acc: number | null;
  coverage: number | null;
}

export interface EvalPage {
  page: number;
  section: string;
  rule_precision: number;
  rule_recall: number;
  rule_f1: number;
  tp: string[];
  fp: string[];
  fn: string[];
  value_correct: number;
  value_wrong: number;
  value_details: unknown[];
  cb_correct: number;
  cb_wrong: number;
  sig_correct: number;
  sig_wrong: number;
  covered: number;
  missing: number;
}

export interface EvalResult {
  aggregate: EvalAggregate;
  pages: EvalPage[];
  document_id: string;
  gold_pages: number;
}

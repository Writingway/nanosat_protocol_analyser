export type Status =
  | "ok"
  | "malformed_line"
  | "unknown_protocol"
  | "empty"
  | "too_long"
  | "framing_error"
  | "too_short"
  | "header_mismatch"
  | "length_mismatch"
  | "crc_error";

export type Direction = "in" | "out";

export interface Capture {
  id: number;
  name: string;
  kind: "import" | "live";
  state: "live" | "ended";
  started_at: string;
  ended_at: string | null;
  frame_count: number;
  created_at: string;
}

export interface Source {
  id: number;
  kind: "file" | "mqtt";
  name: string;
  bench: string;
  equipment: string;
  protocol: string;
}

export interface FieldMeta {
  name: string;
  display: "hex" | "dec";
  size: number;
  description: string;
  values: [number, string][];
}

export interface ProtocolMeta {
  version_id: number;
  sha256: string;
  name: string;
  label: string;
  columns: string[];
  fields: FieldMeta[];
}

export interface CaptureEvent {
  ts: string;
  kind: "connected" | "disconnected";
  message: string;
}

export interface CaptureDetail extends Capture {
  first_ts: string | null;
  sources: Source[];
  protocols: ProtocolMeta[];
  status_counts: Partial<Record<Status, number>>;
  events: CaptureEvent[];
}

export interface FrameRow {
  id: number;
  ts: string;
  ts_bench_rx: string | null;
  received_at: string;
  direction: Direction;
  source: number;
  protocol_version: number | null;
  status: Status;
  detail: string;
  fields: Record<string, number>;
  length: number;
}

export interface FramePage {
  count: number;
  offset: number;
  results: FrameRow[];
}

export interface TreeField {
  name: string;
  offset: number;
  size: number;
  value: number | null;
  label: string | null;
  display: "hex" | "dec";
  description: string;
  issue: string | null;
}

export interface FrameDetail extends FrameRow {
  capture: number;
  raw_hex: string;
  text?: string;
  protocol?: { name: string; label: string; framing: "slip" | "none" };
  data_hex?: string;
  positions?: number[];
  tree?: TreeField[];
  payload?: { offset: number; size: number } | null;
  crc?: {
    offset: number;
    size: number;
    read: number;
    computed: number;
    ok: boolean | null;
    covers: [number, number];
  } | null;
  issues?: { code: Status; message: string }[];
}

export interface LiveState {
  recording: boolean;
  capture: Capture | null;
  ingester_alive: boolean;
  connected: boolean;
  since: string | null;
  last_error: string;
}

export interface LiveStats {
  rate: number;
  queue: number;
  received: number;
  ignored: number;
  capture: number | null;
  written: number;
}

export interface ProtocolStatus {
  file: string;
  name: string | null;
  label: string | null;
  description: string;
  sha256: string | null;
  active: boolean;
  errors: string[];
  meta?: ProtocolMeta;
}

export interface ValidateResult {
  ok: boolean;
  errors: string[];
  name?: string;
  sample_error?: string;
  decoded?: {
    status: Status;
    issues: string[];
    fields: { name: string; value: number | null; label: string | null; issue: string | null }[];
    crc: { read: number; computed: number; ok: boolean | null } | null;
  };
}

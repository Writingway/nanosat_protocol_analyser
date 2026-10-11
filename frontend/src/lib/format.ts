import type { FieldMeta, Status } from "../api/types";

const timeFmt = new Intl.DateTimeFormat("fr-FR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  fractionalSecondDigits: 3,
  hour12: false,
});
const dateTimeFmt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "medium" });

export const fmtTime = (iso: string) => timeFmt.format(new Date(iso));
export const fmtDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));

/** Secondes écoulées depuis `origin`, au format Wireshark (3 décimales). */
export function fmtRelative(iso: string, origin: string) {
  return ((new Date(iso).getTime() - new Date(origin).getTime()) / 1000).toFixed(3);
}

export function fmtDuration(startIso: string, endIso: string | null) {
  const s = Math.max(0, ((endIso ? new Date(endIso) : new Date()).getTime() - new Date(startIso).getTime()) / 1000);
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${Math.round(s % 60)} s`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const hex = (value: number, bytes = 1) => "0x" + value.toString(16).toUpperCase().padStart(bytes * 2, "0");

export function fieldText(value: number, meta?: Pick<FieldMeta, "display" | "size">) {
  return meta?.display === "dec" ? String(value) : hex(value, meta?.size ?? 1);
}

export const STATUS_LABELS: Record<Status, string> = {
  ok: "OK",
  malformed_line: "Ligne illisible",
  unknown_protocol: "Protocole inconnu",
  empty: "Vide",
  too_long: "Trop grande",
  framing_error: "Erreur SLIP",
  too_short: "Trop courte",
  header_mismatch: "En-tête inattendu",
  length_mismatch: "Longueur incohérente",
  crc_error: "CRC faux",
};

export const STATUS_ORDER = Object.keys(STATUS_LABELS) as Status[];

export function hexToBytes(h: string): Uint8Array {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return out;
}

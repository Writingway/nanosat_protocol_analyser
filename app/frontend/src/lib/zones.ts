import type { FrameDetail } from "../api/types";

/** Plage d'octets dans la frame déframée (indices de data_hex). */
export interface ByteRange {
  key: string;
  start: number;
  size: number;
}

export interface Zone extends ByteRange {
  kind: "field" | "payload" | "crc";
  label: string;
  /** Alternance de teinte entre champs voisins, pour les distinguer dans l'hexa. */
  tone: 0 | 1;
}

/** Découpage de la frame en zones (champs d'en-tête, DATA, CRC), partagé par l'arbre et l'hexa. */
export function zonesOf(d: FrameDetail): Zone[] {
  const zones: Zone[] = [];
  (d.tree ?? []).forEach((f, i) => {
    if (f.value !== null)
      zones.push({ key: `f:${f.name}`, kind: "field", label: f.name, start: f.offset, size: f.size, tone: (i % 2) as 0 | 1 });
  });
  if (d.payload && d.payload.size > 0)
    zones.push({ key: "payload", kind: "payload", label: "DATA", start: d.payload.offset, size: d.payload.size, tone: 0 });
  if (d.crc) zones.push({ key: "crc", kind: "crc", label: "CRC", start: d.crc.offset, size: d.crc.size, tone: 0 });
  return zones;
}

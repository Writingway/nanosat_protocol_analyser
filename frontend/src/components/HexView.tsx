import { useMemo, useState } from "react";
import type { FrameDetail } from "../api/types";
import { hexToBytes } from "../lib/format";
import { zonesOf, type ByteRange, type Zone } from "../lib/zones";

interface Props {
  frame: FrameDetail;
  selected: ByteRange | null;
  onSelect: (range: ByteRange | null) => void;
}

const PER_LINE = 16;
const printable = (b: number) => (b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : "·");

/**
 * Vue hexadécimale. Deux modes :
 * - « frame » : octets après retrait du SLIP (ceux que décrit le YAML) ;
 * - « brut » : octets exactement tels que reçus, délimiteurs c0 et échappements compris.
 * Chaque zone (champ, DATA, CRC) a sa teinte ; la zone sélectionnée passe en ambre.
 */
export function HexView({ frame, selected, onSelect }: Props) {
  const hasDeframed = frame.data_hex !== undefined && frame.protocol?.framing === "slip";
  const [mode, setMode] = useState<"frame" | "raw">("frame");
  const showRaw = mode === "raw" || frame.data_hex === undefined;

  const zones = useMemo(() => zonesOf(frame), [frame]);
  const bytes = useMemo(
    () => hexToBytes(showRaw ? frame.raw_hex : frame.data_hex ?? ""),
    [frame, showRaw],
  );

  // Pour chaque octet affiché : la zone à laquelle il appartient (en mode brut, via `positions`).
  const zoneAt = useMemo(() => {
    const out: (Zone | undefined)[] = new Array(bytes.length);
    const rawIndexes = (i: number): number[] => {
      if (!showRaw) return [i];
      const p = frame.positions?.[i];
      if (p === undefined) return [];
      // un octet échappé (db dc ou db dd) occupe deux octets bruts
      const cur = frame.raw_hex.slice(p * 2, p * 2 + 2);
      const next = frame.raw_hex.slice(p * 2 + 2, p * 2 + 4);
      return cur === "db" && (next === "dc" || next === "dd") ? [p, p + 1] : [p];
    };
    for (const z of zones) for (let i = z.start; i < z.start + z.size; i++) rawIndexes(i).forEach((j) => (out[j] = z));
    return out;
  }, [zones, bytes.length, showRaw, frame]);

  const crcClass = frame.crc?.ok === false ? "z-crc-bad" : "z-crc";
  const cls = (i: number) => {
    const z = zoneAt[i];
    if (!z) return showRaw && frame.data_hex !== undefined ? "z-framing" : "";
    const base = z.kind === "crc" ? crcClass : z.kind === "payload" ? "z-payload" : `z-field${z.tone}`;
    return selected?.key === z.key ? `${base} is-selected` : base;
  };
  const click = (i: number) => {
    const z = zoneAt[i];
    onSelect(z && selected?.key !== z.key ? { key: z.key, start: z.start, size: z.size } : null);
  };

  const lines = [];
  for (let off = 0; off < bytes.length; off += PER_LINE) {
    const idx = Array.from({ length: Math.min(PER_LINE, bytes.length - off) }, (_, k) => off + k);
    lines.push(
      <div className="hex-line" key={off}>
        <span className="hex-off">{off.toString(16).padStart(4, "0")}</span>
        <span className="hex-bytes">
          {idx.map((i) => (
            <span key={i} className={`hex-b ${cls(i)} ${i % 8 === 7 ? "gap" : ""}`} onClick={() => click(i)} title={zoneAt[i]?.label}>
              {bytes[i].toString(16).padStart(2, "0")}
            </span>
          ))}
        </span>
        <span className="hex-ascii">
          {idx.map((i) => (
            <span key={i} className={`hex-c ${cls(i)}`} onClick={() => click(i)}>
              {printable(bytes[i])}
            </span>
          ))}
        </span>
      </div>,
    );
  }

  return (
    <div className="hex-view">
      <div className="hex-toolbar">
        {hasDeframed ? (
          <div className="segmented" role="group" aria-label="Octets affichés">
            <button type="button" aria-pressed={!showRaw} onClick={() => setMode("frame")}>Frame</button>
            <button type="button" aria-pressed={showRaw} onClick={() => setMode("raw")}>Brut SLIP</button>
          </div>
        ) : null}
        <span className="muted">{bytes.length} octets</span>
        <span className="hex-legend">
          <span className="z-field0">en-tête</span>
          <span className="z-payload">DATA</span>
          <span className={crcClass}>CRC</span>
          {showRaw && hasDeframed ? <span className="z-framing">SLIP</span> : null}
        </span>
      </div>
      <div className="hex-body mono">{bytes.length ? lines : <p className="empty-note">Frame vide.</p>}</div>
    </div>
  );
}

import type { FrameDetail, Source } from "../api/types";
import { fieldText, fmtDateTime, fmtTime, hex, STATUS_LABELS } from "../lib/format";
import type { ByteRange } from "../lib/zones";

interface Props {
  frame: FrameDetail;
  source?: Source;
  index: number | null;
  selected: ByteRange | null;
  onSelect: (range: ByteRange | null) => void;
}

/** Arbre des champs, façon Wireshark : un clic sur une feuille surligne ses octets dans la vue hexa. */
export function FieldTree({ frame, source, index, selected, onSelect }: Props) {
  const leaf = (range: ByteRange, text: React.ReactNode, warn?: string | null) => {
    const isSel = selected?.key === range.key;
    return (
      <li key={range.key}>
        <button
          type="button"
          className={`tree-leaf ${isSel ? "is-selected" : ""} ${warn ? "is-warn" : ""}`}
          aria-pressed={isSel}
          onClick={() => onSelect(isSel ? null : range)}
        >
          {text}
          {warn ? <span className="tree-warn"> — {warn}</span> : null}
        </button>
      </li>
    );
  };

  const length = frame.data_hex ? frame.data_hex.length / 2 : frame.raw_hex.length / 2;

  return (
    <div className="field-tree" aria-label="Détail de la frame">
      <details open>
        <summary>
          Frame {index != null ? index + 1 : ""} : {length} octets, {STATUS_LABELS[frame.status]}
        </summary>
        <ul>
          <li>Reçue le {fmtDateTime(frame.ts)} à <span className="mono">{fmtTime(frame.ts)}</span> (émission banc)</li>
          {frame.ts_bench_rx ? <li>Réception banc : <span className="mono">{fmtTime(frame.ts_bench_rx)}</span></li> : null}
          <li>Réception analyseur : <span className="mono">{fmtTime(frame.received_at)}</span></li>
          <li>
            Source : {source ? `${source.bench ? source.bench + " › " : ""}${source.equipment}` : "?"}{" "}
            <span className="muted">({source?.name})</span>
          </li>
          <li>Sens : {frame.direction === "in" ? "demande (in)" : "réponse (out)"}</li>
          <li className="muted">Frame n° {frame.id} en base</li>
        </ul>
      </details>

      {frame.text !== undefined ? (
        <details open>
          <summary>Ligne de log illisible</summary>
          <pre className="raw-text">{frame.text}</pre>
          <p className="muted">{frame.detail}</p>
        </details>
      ) : null}

      {frame.protocol && frame.tree ? (
        <details open>
          <summary>
            {frame.protocol.label} {frame.protocol.framing === "slip" ? <span className="muted">(encapsulé SLIP)</span> : null}
          </summary>
          <ul>
            {frame.tree.map((f) =>
              f.value === null ? (
                <li key={f.name} className="muted">{f.name} : absent (frame trop courte)</li>
              ) : (
                leaf(
                  { key: `f:${f.name}`, start: f.offset, size: f.size },
                  <>
                    <strong>{f.name}</strong> : <span className="mono">{fieldText(f.value, f)}</span>
                    {f.label ? ` (${f.label})` : ""}
                    {f.description ? <span className="muted"> — {f.description}</span> : null}
                  </>,
                  f.issue,
                )
              ),
            )}
            {frame.payload && frame.payload.size > 0
              ? leaf({ key: "payload", start: frame.payload.offset, size: frame.payload.size }, <><strong>DATA</strong> : {frame.payload.size} octets <span className="muted">(non décodés)</span></>)
              : null}
            {frame.crc
              ? leaf(
                  { key: "crc", start: frame.crc.offset, size: frame.crc.size },
                  <>
                    <strong>CRC</strong> : <span className="mono">{hex(frame.crc.read, frame.crc.size)}</span>{" "}
                    {frame.crc.ok === null ? (
                      <span className="muted">(non vérifié)</span>
                    ) : frame.crc.ok ? (
                      <span className="ok-text">correct</span>
                    ) : (
                      <span className="bad-text">faux, calculé {hex(frame.crc.computed, frame.crc.size)}</span>
                    )}
                  </>,
                )
              : null}
          </ul>
        </details>
      ) : null}

      {frame.issues && frame.issues.length > 0 ? (
        <details open className="tree-issues">
          <summary>Anomalies ({frame.issues.length})</summary>
          <ul>
            {frame.issues.map((i, n) => (
              <li key={n}>
                <span className="bad-text">{STATUS_LABELS[i.code]}</span> : {i.message}
              </li>
            ))}
          </ul>
        </details>
      ) : frame.status !== "ok" && frame.detail ? (
        <p className="tree-issues bad-text">{frame.detail}</p>
      ) : null}
    </div>
  );
}

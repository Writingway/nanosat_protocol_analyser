import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { FieldMeta, ProtocolMeta, Source } from "../api/types";
import { useFrameWindow } from "../hooks/useFrameWindow";
import { fieldText, fmtRelative, fmtTime } from "../lib/format";
import { StatusChip } from "./StatusChip";

const ROW_HEIGHT = 26;

interface Props {
  captureId: number;
  filters: URLSearchParams;
  protocols: ProtocolMeta[];
  sources: Map<number, Source>;
  origin: string; // horodatage de début de capture, pour la colonne « Temps »
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  /** Id de la frame sélectionnée, connu dès que sa page est chargée. */
  onSelectedId: (id: number | undefined) => void;
  follow: boolean;
  onFollowChange: (follow: boolean) => void;
  onCount: (count: number | undefined) => void;
}

export function FrameList(props: Props) {
  const { captureId, filters, protocols, sources, origin, selectedIndex, onSelect, follow } = props;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<[number, number]>([0, 60]);
  const { count, getRow, error } = useFrameWindow(captureId, filters, range);
  const total = count ?? 0;

  // Colonnes d'en-tête = union des colonnes déclarées dans les YAML des protocoles de la capture.
  const columns = useMemo(() => [...new Set(protocols.flatMap((p) => p.columns))], [protocols]);
  const metaByVersion = useMemo(() => {
    const m = new Map<number, Map<string, FieldMeta>>();
    protocols.forEach((p) => m.set(p.version_id, new Map(p.fields.map((f) => [f.name, f]))));
    return m;
  }, [protocols]);
  const labelsByVersion = useMemo(() => {
    const m = new Map<string, string>();
    protocols.forEach((p) => p.fields.forEach((f) => f.values.forEach(([v, l]) => m.set(`${p.version_id}.${f.name}.${v}`, l))));
    return m;
  }, [protocols]);

  const virtualizer = useVirtualizer({
    count: total,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 30,
  });
  const items = virtualizer.getVirtualItems();
  const firstVisible = items[0]?.index ?? 0;
  const lastVisible = items[items.length - 1]?.index ?? 0;

  useEffect(() => {
    setRange((r) => (r[0] === firstVisible && r[1] === lastVisible ? r : [firstVisible, lastVisible]));
  }, [firstVisible, lastVisible]);

  const { onCount, onSelectedId } = props;
  useEffect(() => onCount(count), [count, onCount]);
  const selectedId = selectedIndex != null ? getRow(selectedIndex)?.id : undefined;
  useEffect(() => onSelectedId(selectedId), [selectedId, onSelectedId]);

  // Mode « Suivre » : reste collé aux dernières frames reçues.
  useEffect(() => {
    if (follow && total > 0) virtualizer.scrollToIndex(total - 1, { align: "end" });
  }, [follow, total, virtualizer]);

  useEffect(() => {
    if (selectedIndex != null && !follow) virtualizer.scrollToIndex(selectedIndex, { align: "auto" });
    // volontairement déclenché seulement quand la sélection change
  }, [selectedIndex]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (!total) return;
    const page = Math.max(1, Math.floor((scrollRef.current?.clientHeight ?? 260) / ROW_HEIGHT) - 1);
    const cur = selectedIndex ?? -1;
    const moves: Record<string, number> = {
      ArrowDown: cur + 1,
      ArrowUp: cur - 1,
      PageDown: cur + page,
      PageUp: cur - page,
      Home: 0,
      End: total - 1,
    };
    if (!(e.key in moves)) return;
    e.preventDefault();
    const next = Math.min(total - 1, Math.max(0, moves[e.key]));
    props.onFollowChange(false);
    onSelect(next);
  };

  const gridTemplate = `64px 108px 88px minmax(140px, 1.4fr) 54px ${columns.map(() => "minmax(90px, 1fr)").join(" ")} 64px 150px`;

  return (
    <div className="frame-list">
      <div className="frame-row frame-head" style={{ gridTemplateColumns: gridTemplate }} role="row">
        <span>N°</span>
        <span>Heure</span>
        <span>Temps (s)</span>
        <span>Source</span>
        <span>Sens</span>
        {columns.map((c) => (
          <span key={c}>{c}</span>
        ))}
        <span className="num">Long.</span>
        <span>Statut</span>
      </div>
      <div
        ref={scrollRef}
        className="frame-scroll"
        tabIndex={0}
        role="grid"
        aria-rowcount={total}
        aria-label="Liste des frames"
        onKeyDown={onKeyDown}
        onWheel={(e) => e.deltaY < 0 && follow && props.onFollowChange(false)}
      >
        {error ? <p className="empty-note">{(error as Error).message}</p> : null}
        {count === 0 ? <p className="empty-note">Aucune frame ne correspond aux filtres.</p> : null}
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {items.map((vi) => {
            const row = getRow(vi.index);
            const selected = vi.index === selectedIndex;
            const src = row ? sources.get(row.source) : undefined;
            const fieldMeta = row?.protocol_version != null ? metaByVersion.get(row.protocol_version) : undefined;
            return (
              <div
                key={vi.key}
                role="row"
                aria-selected={selected}
                className={`frame-row ${row && row.status !== "ok" ? "is-bad" : ""} ${selected ? "is-selected" : ""} ${row?.direction === "out" ? "is-out" : ""}`}
                style={{ gridTemplateColumns: gridTemplate, transform: `translateY(${vi.start}px)`, height: ROW_HEIGHT }}
                onClick={() => {
                  props.onFollowChange(false);
                  onSelect(vi.index);
                }}
              >
                {row ? (
                  <>
                    <span className="num muted">{vi.index + 1}</span>
                    <span className="mono" title={row.ts}>{fmtTime(row.ts)}</span>
                    <span className="mono num">{fmtRelative(row.ts, origin)}</span>
                    <span className="ellipsis" title={src?.name}>
                      {src ? (src.bench ? `${src.bench} › ${src.equipment}` : src.equipment) : "?"}
                    </span>
                    <span className={`dir dir-${row.direction}`}>{row.direction === "in" ? "→ in" : "← out"}</span>
                    {columns.map((c) => {
                      const v = row.fields[c];
                      if (v === undefined) return <span key={c} className="muted">—</span>;
                      const label = labelsByVersion.get(`${row.protocol_version}.${c}.${v}`);
                      return (
                        <span key={c} className="ellipsis" title={label}>
                          <span className="mono">{fieldText(v, fieldMeta?.get(c))}</span>
                          {label ? <span className="muted"> {label}</span> : null}
                        </span>
                      );
                    })}
                    <span className="num mono">{row.length}</span>
                    <span className="ellipsis"><StatusChip status={row.status} title={row.detail} /></span>
                  </>
                ) : (
                  <span className="muted loading-row">…</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

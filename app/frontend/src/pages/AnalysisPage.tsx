import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Status } from "../api/types";
import { FieldTree } from "../components/FieldTree";
import { FilterBar } from "../components/FilterBar";
import { FrameList } from "../components/FrameList";
import { HexView } from "../components/HexView";
import { fmtDateTime, fmtDuration, fmtTime, STATUS_LABELS, STATUS_ORDER } from "../lib/format";
import type { ByteRange } from "../lib/zones";

export function AnalysisPage() {
  const captureId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();

  const capture = useQuery({ queryKey: ["capture", captureId], queryFn: () => api.capture(captureId) });
  const live = useQuery({ queryKey: ["live"], queryFn: api.live });
  const isLive = capture.data?.state === "live";

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | undefined>();
  const [range, setRange] = useState<ByteRange | null>(null);
  const [followPref, setFollow] = useState(true);
  const [count, setCount] = useState<number | undefined>();
  const follow = isLive && followPref;

  const frame = useQuery({
    queryKey: ["frame", selectedId],
    queryFn: () => api.frame(selectedId!),
    enabled: selectedId !== undefined,
    staleTime: Infinity, // une frame enregistrée ne change jamais
  });

  const stop = useMutation({ mutationFn: api.stopLive, onSuccess: () => qc.invalidateQueries() });

  const sources = useMemo(() => new Map((capture.data?.sources ?? []).map((s) => [s.id, s])), [capture.data]);

  const changeFilters = (next: URLSearchParams) => {
    setParams(next, { replace: true });
    setSelectedIndex(null);
    setRange(null);
  };
  const onSelect = useCallback((index: number) => {
    setSelectedIndex(index);
    setRange(null);
  }, []);
  // L'id arrive quand la page de la ligne est chargée ; on garde l'ancien détail en attendant.
  const onSelectedId = useCallback((id: number | undefined) => {
    if (id !== undefined) setSelectedId(id);
  }, []);

  if (capture.isLoading) return <p className="page-note">Chargement de la capture…</p>;
  if (capture.error || !capture.data)
    return (
      <p className="page-note bad-text">
        {(capture.error as Error)?.message ?? "Capture introuvable."} <Link to="/">Retour aux captures</Link>
      </p>
    );

  const c = capture.data;
  const disconnects = c.events.filter((e) => e.kind === "disconnected");
  const statuses = STATUS_ORDER.filter((s) => c.status_counts[s]);
  const filtered = count !== undefined && count !== c.frame_count;

  return (
    <div className="analysis">
      <header className="capture-head">
        <div className="capture-title">
          <h1>{c.name}</h1>
          <p className="muted">
            {c.kind === "live" ? "Capture live" : "Import de fichiers"}, débutée le {fmtDateTime(c.started_at)}, durée{" "}
            {fmtDuration(c.started_at, c.ended_at)}, {c.frame_count.toLocaleString("fr-FR")} frames
            {filtered ? ` (${count!.toLocaleString("fr-FR")} affichées)` : ""}
          </p>
        </div>
        <div className="status-counts" aria-label="Frames par statut (cliquer pour filtrer)">
          {statuses.map((s: Status) => (
            <button
              key={s}
              type="button"
              className={`count-chip ${s === "ok" ? "chip-ok" : "chip-bad"}`}
              aria-pressed={params.get("status") === s}
              onClick={() => {
                const next = new URLSearchParams(params);
                if (params.get("status") === s) next.delete("status");
                else next.set("status", s);
                changeFilters(next);
              }}
            >
              {STATUS_LABELS[s]} <strong>{c.status_counts[s]!.toLocaleString("fr-FR")}</strong>
            </button>
          ))}
        </div>
        {isLive ? (
          <div className="live-controls">
            <label className="toggle">
              <input type="checkbox" checked={followPref} onChange={(e) => setFollow(e.target.checked)} />
              Suivre les nouvelles frames
            </label>
            <button type="button" className="danger" disabled={stop.isPending} onClick={() => stop.mutate()}>
              Arrêter la capture
            </button>
          </div>
        ) : null}
      </header>

      {isLive && live.data && (!live.data.ingester_alive || !live.data.connected) ? (
        <div className="banner banner-bad" role="status">
          {!live.data.ingester_alive
            ? "Le service de capture ne répond plus : aucune frame n'est enregistrée. Relancez-le avec « make ingest »."
            : `Broker MQTT déconnecté${live.data.since ? ` depuis ${fmtTime(live.data.since)}` : ""}. Reconnexion automatique en cours ; les frames émises pendant la coupure sont perdues (QoS 0).`}
        </div>
      ) : null}
      {disconnects.length > 0 ? (
        <details className="banner banner-warn">
          <summary>
            Le broker a été coupé {disconnects.length} fois pendant cette capture : des frames peuvent manquer.
          </summary>
          <ul>
            {c.events.map((e, i) => (
              <li key={i}>
                <span className="mono">{fmtTime(e.ts)}</span> {e.kind === "connected" ? "reconnecté" : "déconnecté"}{" "}
                <span className="muted">{e.message}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <FilterBar captureId={captureId} params={params} onChange={changeFilters} sources={c.sources} protocols={c.protocols} />

      <PanelGroup direction="vertical" autoSaveId="analyse-v" className="panes">
        <Panel defaultSize={55} minSize={20}>
          <FrameList
            captureId={captureId}
            filters={params}
            protocols={c.protocols}
            sources={sources}
            origin={c.first_ts ?? c.started_at}
            selectedIndex={selectedIndex}
            onSelect={onSelect}
            onSelectedId={onSelectedId}
            follow={follow}
            onFollowChange={setFollow}
            onCount={setCount}
          />
        </Panel>
        <PanelResizeHandle className="resize-h" />
        <Panel minSize={15}>
          <PanelGroup direction="horizontal" autoSaveId="analyse-h">
            <Panel defaultSize={50} minSize={20} className="pane">
              {frame.data ? (
                <FieldTree
                  frame={frame.data}
                  source={sources.get(frame.data.source)}
                  index={selectedIndex}
                  selected={range}
                  onSelect={setRange}
                />
              ) : (
                <p className="empty-note">Sélectionnez une frame dans la liste (clic ou flèches ↑ ↓).</p>
              )}
            </Panel>
            <PanelResizeHandle className="resize-v" />
            <Panel minSize={20} className="pane">
              {frame.data ? <HexView frame={frame.data} selected={range} onSelect={setRange} /> : null}
            </Panel>
          </PanelGroup>
        </Panel>
      </PanelGroup>
    </div>
  );
}

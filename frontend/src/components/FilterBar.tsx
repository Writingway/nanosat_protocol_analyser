import { useState, type FormEvent } from "react";
import { exportUrl } from "../api/client";
import type { ProtocolMeta, Source } from "../api/types";
import { STATUS_LABELS, STATUS_ORDER } from "../lib/format";

interface Props {
  captureId: number;
  params: URLSearchParams;
  onChange: (next: URLSearchParams) => void;
  sources: Source[];
  protocols: ProtocolMeta[];
}

/** ISO (UTC) ↔ valeur d'un <input type="datetime-local"> (heure locale). */
const toLocalInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 23);
};
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : "");

export function FilterBar({ captureId, params, onChange, sources, protocols }: Props) {
  const fieldNames = [...new Set(protocols.flatMap((p) => p.fields.map((f) => f.name)))];
  const [field, setField] = useState(fieldNames[0] ?? "");
  const [value, setValue] = useState("");
  const [valueError, setValueError] = useState("");

  const set = (key: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(key, v);
    else next.delete(key);
    next.delete("frame");
    onChange(next);
  };

  const fieldFilters = [...params.entries()].filter(([k]) => k.startsWith("f."));

  const addField = (e: FormEvent) => {
    e.preventDefault();
    const parts = value.split(/[\s,;]+/).filter(Boolean);
    if (!field || parts.length === 0) return;
    if (parts.some((p) => Number.isNaN(Number(p)))) {
      setValueError("Valeur attendue en décimal (42) ou en hexadécimal (0x2A).");
      return;
    }
    setValueError("");
    const key = `f.${field}`;
    const existing = params.get(key)?.split(",") ?? [];
    set(key, [...new Set([...existing, ...parts])].join(","));
    setValue("");
  };

  const active = [...params.keys()].some((k) => k !== "frame");

  return (
    <div className="filter-bar">
      <label>
        Sens
        <select value={params.get("direction") ?? ""} onChange={(e) => set("direction", e.target.value)}>
          <option value="">Tous</option>
          <option value="in">Demandes (in)</option>
          <option value="out">Réponses (out)</option>
        </select>
      </label>
      <label>
        Statut
        <select value={params.get("status") ?? ""} onChange={(e) => set("status", e.target.value)}>
          <option value="">Tous</option>
          <option value="errors">En erreur</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
      </label>
      {sources.length > 1 ? (
        <label>
          Source
          <select value={params.get("source") ?? ""} onChange={(e) => set("source", e.target.value)}>
            <option value="">Toutes</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.bench ? `${s.bench} › ` : ""}{s.equipment} — {s.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {fieldNames.length > 0 ? (
        <form className="field-filter" onSubmit={addField}>
          <label>
            Champ
            <select value={field} onChange={(e) => setField(e.target.value)}>
              {fieldNames.map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label>
            =
            <input
              className="mono"
              size={9}
              placeholder="0x2A"
              value={value}
              aria-invalid={!!valueError}
              onChange={(e) => setValue(e.target.value)}
            />
          </label>
          <button type="submit">Filtrer</button>
        </form>
      ) : null}

      <label>
        Du
        <input type="datetime-local" step="0.001" value={toLocalInput(params.get("from"))} onChange={(e) => set("from", fromLocalInput(e.target.value))} />
      </label>
      <label>
        au
        <input type="datetime-local" step="0.001" value={toLocalInput(params.get("to"))} onChange={(e) => set("to", fromLocalInput(e.target.value))} />
      </label>

      {fieldFilters.map(([k, v]) => (
        <span className="filter-pill" key={k}>
          <span className="mono">{k.slice(2)} = {v.split(",").join(" ou ")}</span>
          <button type="button" aria-label={`Retirer le filtre ${k.slice(2)}`} onClick={() => set(k, "")}>×</button>
        </span>
      ))}
      {active ? (
        <button type="button" className="link" onClick={() => onChange(new URLSearchParams())}>
          Effacer les filtres
        </button>
      ) : null}
      {valueError ? <span className="bad-text" role="alert">{valueError}</span> : null}

      <span className="filter-spacer" />
      <span className="export-links">
        Exporter
        <a href={exportUrl(captureId, "csv", params)} download>CSV</a>
        <a href={exportUrl(captureId, "log", params, "in")} download title="Format du banc, ré-importable">log in</a>
        <a href={exportUrl(captureId, "log", params, "out")} download title="Format du banc, ré-importable">log out</a>
      </span>
    </div>
  );
}

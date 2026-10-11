import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Direction } from "../api/types";
import { useLiveStream } from "../hooks/useLiveStream";
import { fmtDateTime, fmtDuration } from "../lib/format";

export function CapturesPage() {
  return (
    <div className="page captures-page">
      <div className="captures-top">
        <LiveCard />
        <ImportCard />
      </div>
      <CaptureTable />
    </div>
  );
}

function LiveCard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { stats } = useLiveStream();
  const live = useQuery({ queryKey: ["live"], queryFn: api.live });
  const [name, setName] = useState("");
  const start = useMutation({
    mutationFn: () => api.startLive(name),
    onSuccess: (s) => {
      setName("");
      qc.invalidateQueries();
      if (s.capture) navigate(`/captures/${s.capture.id}`);
    },
  });
  const stop = useMutation({ mutationFn: api.stopLive, onSuccess: () => qc.invalidateQueries() });
  const s = live.data;

  return (
    <section className="card" aria-labelledby="live-title">
      <h2 id="live-title">Capture live MQTT</h2>
      {!s ? (
        <p className="muted">Lecture de l'état…</p>
      ) : !s.ingester_alive ? (
        <p className="bad-text">
          Le service de capture ne tourne pas. Lancez-le dans un terminal : <code>make ingest</code>
        </p>
      ) : (
        <p className={s.connected ? "" : "bad-text"}>
          {s.connected ? "Broker connecté" : `Broker déconnecté : ${s.last_error || "reconnexion en cours"}`}
          {stats ? <span className="muted">, {Math.round(stats.rate)} messages/s reçus</span> : null}
        </p>
      )}

      {s?.recording && s.capture ? (
        <div className="live-running">
          <p>
            Enregistrement de <Link to={`/captures/${s.capture.id}`}>{s.capture.name}</Link> depuis{" "}
            {fmtDuration(s.capture.started_at, null)}
            {stats?.capture === s.capture.id ? `, ${stats.written.toLocaleString("fr-FR")} frames` : ""}.
          </p>
          <div className="row">
            <Link className="button" to={`/captures/${s.capture.id}`}>Voir en direct</Link>
            <button type="button" className="danger" disabled={stop.isPending} onClick={() => stop.mutate()}>
              Arrêter la capture
            </button>
          </div>
        </div>
      ) : (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <label className="grow">
            Nom de la capture
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ex. Essai thermique roue X" />
          </label>
          <button type="submit" className="primary" disabled={start.isPending}>
            Démarrer la capture
          </button>
        </form>
      )}
      {start.error ? <p className="bad-text" role="alert">{(start.error as Error).message}</p> : null}
      <p className="muted small">
        L'analyseur écoute seulement : il n'envoie jamais rien aux équipements. Les topics suivis sont définis dans
        config/ingest.yaml.
      </p>
    </section>
  );
}

interface PickedFile {
  file: File;
  direction: Direction;
}

const guessDirection = (name: string): Direction => (/out(\.\w+)?$/i.test(name) ? "out" : "in");

function ImportCard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const protocols = useQuery({ queryKey: ["protocols"], queryFn: api.protocols });
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [equipment, setEquipment] = useState("");
  const [protocol, setProtocol] = useState("");
  const [bench, setBench] = useState("");
  const [over, setOver] = useState(false);

  const active = (protocols.data ?? []).filter((p) => p.active && p.name);
  const chosenProtocol = protocol || active[0]?.name || "";

  const upload = useMutation({
    mutationFn: (force: boolean) => {
      const form = new FormData();
      const ins = files.filter((f) => f.direction === "in");
      const outs = files.filter((f) => f.direction === "out");
      if (ins[0]) form.append("file_in", ins[0].file);
      if (outs[0]) form.append("file_out", outs[0].file);
      form.append("equipment", equipment);
      form.append("protocol", chosenProtocol);
      form.append("bench", bench);
      if (force) form.append("force", "1");
      return api.importCapture(form);
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["captures"] });
      qc.invalidateQueries({ queryKey: ["sources"] });
      navigate(`/captures/${c.id}`);
    },
  });

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const picked = [...files];
    for (const file of Array.from(list)) {
      const direction = guessDirection(file.name.replace(/\.[^.]+$/, ""));
      const i = picked.findIndex((p) => p.direction === direction);
      if (i >= 0) picked.splice(i, 1); // un fichier par sens
      picked.push({ file, direction });
    }
    setFiles(picked.slice(-2));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    addFiles(e.dataTransfer.files);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    upload.mutate(false);
  };

  const err = upload.error as ApiError | null;
  const duplicateOf = err?.status === 409 ? (err.body.capture as number) : null;
  const directions = new Set(files.map((f) => f.direction));

  return (
    <section className="card" aria-labelledby="import-title">
      <h2 id="import-title">Importer des logs</h2>
      <form onSubmit={submit} className="import-form">
        <label
          className={`dropzone ${over ? "is-over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <input type="file" multiple accept=".txt,.log" onChange={(e) => addFiles(e.target.files)} />
          {files.length === 0 ? (
            <span>Déposez ici le fichier des demandes (in) et celui des réponses (out), ou cliquez pour les choisir.</span>
          ) : (
            <span>Fichiers choisis :</span>
          )}
        </label>
        {files.length > 0 ? (
          <ul className="picked">
            {files.map((f, i) => (
              <li key={f.file.name}>
                <span className="mono ellipsis">{f.file.name}</span>
                <select
                  aria-label={`Sens de ${f.file.name}`}
                  value={f.direction}
                  onChange={(e) =>
                    setFiles(files.map((x, j) => (j === i ? { ...x, direction: e.target.value as Direction } : x)))
                  }
                >
                  <option value="in">demandes (in)</option>
                  <option value="out">réponses (out)</option>
                </select>
                <button type="button" className="link" onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                  Retirer
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {files.length === 2 && directions.size === 1 ? (
          <p className="bad-text small">Les deux fichiers ont le même sens : corrigez l'un des deux.</p>
        ) : null}

        <div className="row">
          <label className="grow">
            Équipement
            <input
              required
              list="equipments"
              value={equipment}
              onChange={(e) => setEquipment(e.target.value)}
              placeholder="ex. gyro"
            />
            <datalist id="equipments">
              {[...new Set((sources.data ?? []).map((s) => s.equipment))].map((eq) => (
                <option key={eq} value={eq} />
              ))}
            </datalist>
          </label>
          <label>
            Protocole
            <select value={chosenProtocol} onChange={(e) => setProtocol(e.target.value)}>
              {active.map((p) => (
                <option key={p.name} value={p.name!}>{p.label}</option>
              ))}
            </select>
          </label>
          <label>
            Banc <span className="muted">(facultatif)</span>
            <input value={bench} onChange={(e) => setBench(e.target.value)} placeholder="ex. banc1" />
          </label>
        </div>
        <div className="row">
          <button
            type="submit"
            className="primary"
            disabled={upload.isPending || files.length === 0 || !equipment || (files.length === 2 && directions.size === 1)}
          >
            {upload.isPending ? "Import en cours…" : "Importer"}
          </button>
        </div>
        {err ? (
          <div className="bad-text" role="alert">
            <p style={{ whiteSpace: "pre-line" }}>{err.message}</p>
            {duplicateOf ? (
              <p>
                <Link to={`/captures/${duplicateOf}`}>Ouvrir la capture existante</Link> ou{" "}
                <button type="button" className="link" onClick={() => upload.mutate(true)}>importer quand même</button>
              </p>
            ) : null}
          </div>
        ) : null}
      </form>
    </section>
  );
}

function CaptureTable() {
  const qc = useQueryClient();
  const captures = useQuery({ queryKey: ["captures"], queryFn: api.captures });
  const remove = useMutation({
    mutationFn: api.deleteCapture,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["captures"] }),
  });

  return (
    <section aria-labelledby="list-title">
      <h2 id="list-title">Captures</h2>
      {remove.error ? <p className="bad-text" role="alert">{(remove.error as Error).message}</p> : null}
      {captures.error ? <p className="bad-text">{(captures.error as Error).message}</p> : null}
      {captures.data?.length === 0 ? (
        <p className="empty-note">Aucune capture pour l'instant. Importez des logs ou démarrez une capture live.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Origine</th>
              <th>Début</th>
              <th>Durée</th>
              <th className="num">Frames</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(captures.data ?? []).map((c) => (
              <tr key={c.id}>
                <td>
                  <Link to={`/captures/${c.id}`}>{c.name}</Link>
                  {c.state === "live" ? <span className="tag-live">en cours</span> : null}
                </td>
                <td>{c.kind === "live" ? "Live MQTT" : "Import"}</td>
                <td>{fmtDateTime(c.started_at)}</td>
                <td>{fmtDuration(c.started_at, c.ended_at)}</td>
                <td className="num mono">{c.frame_count.toLocaleString("fr-FR")}</td>
                <td className="num">
                  {c.state !== "live" ? (
                    <button
                      type="button"
                      className="link"
                      onClick={() => {
                        if (confirm(`Supprimer définitivement « ${c.name} » et ses ${c.frame_count} frames ?`))
                          remove.mutate(c.id);
                      }}
                    >
                      Supprimer
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

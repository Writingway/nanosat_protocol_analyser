import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ValidateResult } from "../api/types";
import { fieldText, hex, STATUS_LABELS } from "../lib/format";

const TEMPLATE = (name: string) => `# Nouveau protocole : décrire l'en-tête (voir docs/GUIDE_YAML.md)
name: ${name}
label: "${name}"
framing: none          # slip si les frames sont encadrées par c0
byte_order: big
min_length: 5
max_length: 256
fields:
  - {name: DST,  offset: 0, size: 1, description: "Adresse destinataire"}
  - {name: SRC,  offset: 1, size: 1, description: "Adresse source"}
  - {name: CTRL, offset: 2, size: 1, description: "Contrôle"}
payload: {offset: 3, end: -2}
crc: {type: crc16_ccitt_false, offset: -2, byte_order: little, from: 0, to: -2}
`;

export function ProtocolsPage() {
  const protocols = useQuery({ queryKey: ["protocols"], queryFn: api.protocols, refetchInterval: 3000 });
  const [params, setParams] = useSearchParams();
  const current = params.get("p") ?? protocols.data?.find((p) => p.name)?.name ?? null;

  return (
    <div className="page protocols-page">
      <aside className="proto-list" aria-label="Protocoles">
        <h2>Protocoles</h2>
        <ul>
          {(protocols.data ?? []).map((p) => (
            <li key={p.file}>
              <button
                type="button"
                className={`proto-item ${current === p.name ? "is-selected" : ""}`}
                onClick={() => p.name && setParams({ p: p.name })}
                disabled={!p.name}
              >
                <strong>{p.label ?? p.file}</strong>
                <span className="muted small">{p.file}</span>
                {p.errors.length ? (
                  <span className="bad-text small">
                    {p.active ? "Dernière modification refusée" : "Invalide, non chargé"}
                  </span>
                ) : (
                  <span className="ok-text small">Actif, version {p.sha256?.slice(0, 8)}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => {
            const name = prompt("Nom du nouveau protocole (minuscules, chiffres, - ou _) :")?.trim();
            if (name) setParams({ p: name, new: "1" });
          }}
        >
          Nouveau protocole
        </button>
      </aside>
      {current ? <ProtocolEditor key={current} name={current} isNew={params.get("new") === "1"} /> : null}
    </div>
  );
}

function ProtocolEditor({ name, isNew }: { name: string; isNew: boolean }) {
  const qc = useQueryClient();
  const source = useQuery({ queryKey: ["protocol", name], queryFn: () => api.protocolYaml(name), enabled: !isNew });
  const [text, setText] = useState(isNew ? TEMPLATE(name) : "");
  const [sample, setSample] = useState("");
  const [result, setResult] = useState<ValidateResult | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (source.data) setText(source.data.yaml);
  }, [source.data]);

  const validate = useMutation({ mutationFn: () => api.validateProtocol(text, sample), onSuccess: setResult });
  const save = useMutation({
    mutationFn: () => api.saveProtocol(name, text),
    onSuccess: () => {
      setSaved(true);
      setResult(null);
      qc.invalidateQueries({ queryKey: ["protocols"] });
      qc.invalidateQueries({ queryKey: ["protocol", name] });
    },
  });

  const fileErrors = source.data?.status?.errors ?? [];
  const saveErrors = (save.error as { body?: { errors?: string[] } } | null)?.body?.errors ?? [];

  return (
    <section className="proto-editor" aria-label={`Édition de ${name}`}>
      <h2>{name}.yaml</h2>
      {fileErrors.length ? (
        <div className="banner banner-bad">
          <p>Le fichier sur disque contient des erreurs ; l'analyseur utilise toujours la version précédente.</p>
          <ul>{fileErrors.map((e) => <li key={e} className="mono">{e}</li>)}</ul>
        </div>
      ) : null}
      <textarea
        className="yaml mono"
        spellCheck={false}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setSaved(false);
        }}
        aria-label="Contenu YAML"
      />
      <div className="row">
        <label className="grow">
          Frame d'essai en hexadécimal <span className="muted">(facultatif, copiée depuis un log)</span>
          <input className="mono" value={sample} onChange={(e) => setSample(e.target.value)} placeholder="c02a11840a90003045bec0" />
        </label>
        <button type="button" onClick={() => validate.mutate()} disabled={validate.isPending}>
          Vérifier
        </button>
        <button type="button" className="primary" onClick={() => save.mutate()} disabled={save.isPending}>
          Enregistrer
        </button>
      </div>
      {saved ? <p className="ok-text" role="status">Enregistré. Les nouvelles frames utilisent cette version.</p> : null}
      {saveErrors.length ? (
        <div className="banner banner-bad" role="alert">
          <p>Non enregistré : corrigez d'abord ces erreurs.</p>
          <ul>{saveErrors.map((e) => <li key={e} className="mono">{e}</li>)}</ul>
        </div>
      ) : null}
      {result ? <ValidationResult r={result} /> : null}
    </section>
  );
}

function ValidationResult({ r }: { r: ValidateResult }) {
  if (!r.ok)
    return (
      <div className="banner banner-bad" role="alert">
        <p>Description invalide :</p>
        <ul>{r.errors.map((e) => <li key={e} className="mono">{e}</li>)}</ul>
      </div>
    );
  return (
    <div className="banner banner-ok" role="status">
      <p>Description valide.</p>
      {r.sample_error ? <p className="bad-text">Frame d'essai : {r.sample_error}</p> : null}
      {r.decoded ? (
        <>
          <p>
            Frame d'essai : <strong>{STATUS_LABELS[r.decoded.status]}</strong>
          </p>
          <ul>
            {r.decoded.fields.map((f) => (
              <li key={f.name}>
                {f.name} : {f.value === null ? "absent" : <span className="mono">{fieldText(f.value)}</span>}
                {f.label ? ` (${f.label})` : ""} {f.issue ? <span className="bad-text">{f.issue}</span> : null}
              </li>
            ))}
            {r.decoded.crc ? (
              <li>
                CRC lu <span className="mono">{hex(r.decoded.crc.read, 2)}</span>, calculé{" "}
                <span className="mono">{hex(r.decoded.crc.computed, 2)}</span>
              </li>
            ) : null}
            {r.decoded.issues.map((i) => (
              <li key={i} className="bad-text">{i}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

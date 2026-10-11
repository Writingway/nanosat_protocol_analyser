import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { LiveStats } from "../api/types";

interface StreamState {
  /** Le navigateur reçoit-il le flux temps réel du serveur ? */
  online: boolean;
  stats: LiveStats | null;
}

const StreamContext = createContext<StreamState>({ online: false, stats: null });

/** Délai minimal entre deux rafraîchissements d'une même capture : l'affichage suit sans saturer l'API. */
const REFRESH_MS = 500;

/**
 * Une seule connexion SSE pour toute l'application. Les événements ne contiennent pas
 * les frames : ils invalident les requêtes concernées, et seules les lignes visibles sont rechargées.
 */
export function LiveStreamProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>({ online: false, stats: null });

  useEffect(() => {
    const pending = new Map<number, number>();
    const refreshCapture = (captureId: number) => {
      if (pending.has(captureId)) return;
      pending.set(
        captureId,
        window.setTimeout(() => {
          pending.delete(captureId);
          qc.invalidateQueries({ queryKey: ["frames", captureId] });
          qc.invalidateQueries({ queryKey: ["capture", captureId] });
          qc.invalidateQueries({ queryKey: ["captures"] });
        }, REFRESH_MS),
      );
    };

    // EventSource se reconnecte tout seul après une coupure (délai « retry » envoyé par le serveur).
    const es = new EventSource("/api/stream/");
    es.onopen = () => {
      setState((s) => ({ ...s, online: true }));
      qc.invalidateQueries({ queryKey: ["live"] });
    };
    es.onerror = () => setState((s) => ({ ...s, online: false }));
    es.addEventListener("frames", (e) => refreshCapture(JSON.parse((e as MessageEvent).data).capture));
    es.addEventListener("live", () => {
      qc.invalidateQueries({ queryKey: ["live"] });
      qc.invalidateQueries({ queryKey: ["captures"] });
      qc.invalidateQueries({ queryKey: ["capture"] });
    });
    es.addEventListener("stats", (e) => setState({ online: true, stats: JSON.parse((e as MessageEvent).data) }));

    return () => {
      es.close();
      pending.forEach((t) => clearTimeout(t));
    };
  }, [qc]);

  return <StreamContext.Provider value={state}>{children}</StreamContext.Provider>;
}

export const useLiveStream = () => useContext(StreamContext);

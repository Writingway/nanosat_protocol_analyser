import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useLiveStream } from "../hooks/useLiveStream";
import { fmtTime } from "../lib/format";

/** État du live en un coup d'œil, visible depuis toutes les pages. */
export function LiveBadge() {
  const { online, stats } = useLiveStream();
  const { data } = useQuery({ queryKey: ["live"], queryFn: api.live, refetchInterval: 5000 });

  let tone = "idle";
  let text = "Live : en attente";
  if (!online) {
    tone = "bad";
    text = "Serveur injoignable";
  } else if (data && !data.ingester_alive) {
    tone = "bad";
    text = "Service de capture arrêté";
  } else if (data && !data.connected) {
    tone = "bad";
    text = `Broker déconnecté${data.since ? ` depuis ${fmtTime(data.since)}` : ""}`;
  } else if (data?.recording) {
    tone = "rec";
    text = `Enregistrement en cours${stats ? `, ${Math.round(stats.rate)} frames/s` : ""}`;
  } else if (data) {
    tone = "ok";
    text = "Broker connecté";
  }

  const body = (
    <span className={`live-badge live-${tone}`} title={data?.last_error || undefined}>
      <span className="live-dot" aria-hidden />
      {text}
    </span>
  );
  return data?.recording && data.capture ? <Link to={`/captures/${data.capture.id}`}>{body}</Link> : body;
}

import type { Status } from "../api/types";
import { STATUS_LABELS } from "../lib/format";

export function StatusChip({ status, title }: { status: Status; title?: string }) {
  return (
    <span className={`chip chip-${status === "ok" ? "ok" : "bad"}`} title={title || undefined}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

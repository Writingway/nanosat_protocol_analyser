import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "../api/client";
import type { FramePage, FrameRow } from "../api/types";

export const PAGE_SIZE = 200;

/**
 * Charge uniquement les pages de frames couvrant la zone visible de la liste.
 * Une capture de 500 000 frames ne coûte donc que 1 à 3 pages de 200 lignes à l'écran.
 */
export function useFrameWindow(captureId: number, filters: URLSearchParams, visible: [number, number]) {
  const filterKey = filters.toString();
  const first = Math.floor(Math.max(0, visible[0]) / PAGE_SIZE);
  const last = Math.floor(Math.max(0, visible[1]) / PAGE_SIZE);
  const pages = useMemo(() => {
    const out: number[] = [];
    for (let p = first; p <= last; p++) out.push(p);
    return out;
  }, [first, last]);

  const results = useQueries({
    queries: pages.map((page) => ({
      queryKey: ["frames", captureId, filterKey, page],
      queryFn: (): Promise<FramePage> => {
        const p = new URLSearchParams(filters);
        p.delete("frame");
        p.set("capture", String(captureId));
        p.set("offset", String(page * PAGE_SIZE));
        p.set("limit", String(PAGE_SIZE));
        return api.frames(p);
      },
      // garde les lignes affichées pendant le rechargement (pas de clignotement en live)
      placeholderData: (previous: FramePage | undefined) => previous,
      staleTime: 10_000,
    })),
  });

  const byPage = new Map<number, FrameRow[]>();
  let count: number | undefined;
  results.forEach((r, i) => {
    if (r.data) {
      byPage.set(pages[i], r.data.results);
      count = r.data.count;
    }
  });
  const error = results.find((r) => r.error)?.error ?? null;

  const getRow = (index: number): FrameRow | undefined =>
    byPage.get(Math.floor(index / PAGE_SIZE))?.[index % PAGE_SIZE];

  return { count, getRow, error, loading: results.some((r) => r.isLoading) };
}

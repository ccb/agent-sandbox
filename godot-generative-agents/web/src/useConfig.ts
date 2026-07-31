// Thin React wrapper over config/configApi.fetchConfig. Fetches GET /config once a
// backend base is present; re-fetch via refetch() (e.g. after a reset re-opens
// the gate). Kept thin on purpose — the classifying logic and its tests live in
// config/configApi (the package tests logic, not rendered hooks).

import { useCallback, useEffect, useState } from "react";
import { fetchConfig } from "./config/configApi";
import type { ConfigStatus, ConfigSurface } from "./types/config";

export function useConfig(base: string | null): {
  status: ConfigStatus;
  surface: ConfigSurface | null;
  refetch: () => void;
} {
  const [status, setStatus] = useState<ConfigStatus>("loading");
  const [surface, setSurface] = useState<ConfigSurface | null>(null);
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  // nonce is a write-only trigger — refetch() bumps it to force this effect to
  // re-run; the body never reads it, so it can't join the dep list via use.
  // biome-ignore lint/correctness/useExhaustiveDependencies: nonce triggers refetch()
  useEffect(() => {
    if (!base) {
      setStatus("unavailable");
      setSurface(null);
      return;
    }
    let cancelled = false;
    setStatus("loading");
    fetchConfig(base).then((r) => {
      if (cancelled) return;
      setStatus(r.status);
      setSurface(r.surface ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [base, nonce]);

  return { status, surface, refetch };
}

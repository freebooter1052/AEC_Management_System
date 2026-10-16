import { useEffect, useRef, useState } from "react";

/**
 * Runs at most one call of an async function at a time: a call made while another is in flight is dropped
 * (returns undefined). `onBusy(true|false)` reports the state. The flag always resets, even after an error,
 * so a failed request can be retried.
 */
export function singleFlight(onBusy) {
  let inFlight = false;
  return async (fn) => {
    if (inFlight) return undefined;
    inFlight = true;
    onBusy?.(true);
    try {
      return await fn();
    } finally {
      inFlight = false;
      onBusy?.(false);
    }
  };
}

/**
 * Guard for an async action (save, delete, status change): `run(fn)` starts it only when nothing is in
 * flight, so a double click sends one request - the flag is set synchronously, before React re-renders.
 * `busy` drives the disabled button and its "Saving…" label.
 */
export function useSubmit() {
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const guard = useRef(null);
  if (!guard.current) guard.current = singleFlight((b) => { if (mounted.current) setBusy(b); });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  return [busy, guard.current];
}

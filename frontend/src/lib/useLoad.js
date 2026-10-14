import { useCallback, useEffect, useRef, useState } from "react";

/** Run an async loader when `deps` change; ignores responses that arrive after a newer request. */
export function useLoad(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const run = useCallback(loader, deps); // the loader is re-created on every render; `deps` decide when it reloads

  const reload = useCallback(() => {
    const id = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    return run().then(
      (data) => { if (id === seq.current) setState({ data, error: null, loading: false }); },
      (error) => { if (id === seq.current) setState({ data: null, error, loading: false }); },
    );
  }, [run]);

  useEffect(() => { reload(); }, [reload]);

  const setData = useCallback((update) => setState((s) => ({ ...s, data: typeof update === "function" ? update(s.data) : update })), []);
  return { ...state, reload, setData };
}

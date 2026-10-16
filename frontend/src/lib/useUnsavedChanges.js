import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

/**
 * While `dirty`, leaving the page asks first: closing or reloading the tab shows the browser's own prompt,
 * and clicking any in-app link is held back (`pending` is its address) until the page calls `leave()` or
 * `stay()`. Nothing is saved or discarded automatically.
 */
export function useUnsavedChanges(dirty) {
  const navigate = useNavigate();
  const [pending, setPending] = useState(null);

  useEffect(() => {
    if (!dirty) return undefined;
    const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = ""; };
    // Capture phase on document runs before React Router's link handler, so the navigation can be held.
    const onClick = (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest?.("a[href]");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin) return; // leaving the site: the beforeunload prompt covers it
      if (url.pathname === window.location.pathname && url.search === window.location.search) return; // same page (e.g. "#")
      e.preventDefault();
      e.stopPropagation();
      setPending(url.pathname + url.search + url.hash);
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);

  return {
    pending,
    stay: () => setPending(null),
    leave: () => { const to = pending; setPending(null); if (to) navigate(to); },
  };
}

import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(() => {});
let seq = 0;

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const toast = useCallback((message, kind = "info") => {
    const id = ++seq;
    setItems((list) => [...list, { id, message, kind }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={toast}>
      {children}
      {items.length > 0 && (
        <div className="toast-host" role="status">
          {items.map((t) => <div key={t.id} className={"toast" + (t.kind === "error" ? " error" : "")}>{t.message}</div>)}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

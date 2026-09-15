import { useEffect, useState } from "react";
import api from "../api/client";

export function useApi(path, { skip = false } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!skip);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (skip || !path) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get(path)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, skip, tick]);

  const reload = () => setTick((t) => t + 1);

  return { data, error, loading, reload };
}

export default useApi;

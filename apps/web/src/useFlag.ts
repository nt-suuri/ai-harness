import { useEffect, useState } from "react";

interface FlagsResponse {
  [name: string]: unknown;
}

let cachedFlags: FlagsResponse | null = null;
let fetchPromise: Promise<FlagsResponse | null> | null = null;

function truthy(v: unknown): boolean {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  if (typeof v === "string")
    return ["true", "1", "yes", "on"].includes(v.trim().toLowerCase());
  return false;
}

async function fetchFlags(): Promise<FlagsResponse | null> {
  try {
    const resp = await fetch("/api/flags");
    if (!resp.ok) return null;
    return (await resp.json()) as FlagsResponse;
  } catch {
    return null;
  }
}

export function useFlag(name: string): boolean {
  const [enabled, setEnabled] = useState<boolean>(() =>
    cachedFlags ? truthy(cachedFlags[name]) : false,
  );

  useEffect(() => {
    if (cachedFlags !== null) {
      setEnabled(truthy(cachedFlags[name]));
      return;
    }
    if (fetchPromise === null) {
      fetchPromise = fetchFlags().then((data) => {
        cachedFlags = data ?? {};
        return cachedFlags;
      });
    }
    fetchPromise.then((data) => {
      if (data) setEnabled(truthy(data[name]));
    });
  }, [name]);

  return enabled;
}

export function _resetFlagsCache(): void {
  cachedFlags = null;
  fetchPromise = null;
}

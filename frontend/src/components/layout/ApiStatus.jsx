import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SHELL } from "@/constants/testIds";
import { cn } from "@/lib/utils";

const LABELS = { loading: "Checking systems", ok: "All systems operational", down: "Service degraded" };

export const ApiStatus = () => {
  const [state, setState] = useState("loading");

  useEffect(() => {
    api.get("/health")
      .then(({ data }) => setState(data.status === "ok" ? "ok" : "down"))
      .catch(() => setState("down"));
  }, []);

  return (
    <span data-testid={SHELL.apiStatus} data-status={state} className="inline-flex items-center gap-2 text-xs text-av-linen/70">
      <span className={cn("h-2 w-2 rounded-full",
        state === "ok" && "bg-emerald-400", state === "down" && "bg-red-400", state === "loading" && "bg-av-gold animate-pulse")} />
      {LABELS[state]}
    </span>
  );
};

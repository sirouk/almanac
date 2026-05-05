export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    ["healthy", "active", "paid", "contacted", "recorded", "complete", "completed", "success", "ready"].includes(normalized)
      ? "border-neon-green/30 bg-neon-green/10 text-neon-green"
      : ["degraded", "pending", "queued", "provisioning", "retrying", "not provisioned", "pending run", "pending credentialed run"].includes(normalized)
        ? "border-yellow-400/30 bg-yellow-400/10 text-yellow-300"
        : ["unknown", "not_configured", "not configured", "missing"].includes(normalized)
          ? "border-soft-white/15 bg-soft-white/5 text-soft-white/50"
        : "border-red-400/30 bg-red-500/10 text-red-300";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tone}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function ErrorAlert({ message, className }: { message: string; className?: string }) {
  return (
    <div className={`rounded bg-red-900/40 px-4 py-2 text-sm text-red-300 ${className ?? ""}`}>
      {message}
    </div>
  );
}

export function LoadingSpinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 text-soft-white/40">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-soft-white/20 border-t-signal-orange" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  );
}

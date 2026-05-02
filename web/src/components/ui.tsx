export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const color =
    ["healthy", "active", "paid", "contacted", "recorded", "complete", "completed", "success"].includes(normalized)
      ? "text-neon-green"
      : ["degraded", "pending", "queued", "provisioning", "retrying", "not provisioned"].includes(normalized)
        ? "text-yellow-400"
        : ["unknown", "not_configured", "not configured", "missing"].includes(normalized)
          ? "text-soft-white/40"
        : "text-red-400";
  return <span className={`text-xs font-semibold uppercase ${color}`}>{status.replaceAll("_", " ")}</span>;
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

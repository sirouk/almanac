export function StatusBadge({ status }: { status: string }) {
  const color =
    status === "healthy" || status === "active" || status === "paid"
      ? "text-neon-green"
      : status === "degraded" || status === "pending" || status === "queued"
        ? "text-yellow-400"
        : "text-red-400";
  return <span className={`text-xs font-semibold uppercase ${color}`}>{status}</span>;
}

export function ErrorAlert({ message, className }: { message: string; className?: string }) {
  return (
    <div className={`rounded bg-red-900/40 px-4 py-2 text-sm text-red-300 ${className ?? ""}`}>
      {message}
    </div>
  );
}

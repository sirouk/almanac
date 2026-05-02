"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import { ErrorAlert } from "@/components/ui";
import { useRouter } from "next/navigation";

type LoginKind = "user" | "admin";

export default function LoginPage() {
  const router = useRouter();
  const [kind, setKind] = useState<LoginKind>("user");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.login(kind, { email });
      if (res.status === 201) {
        router.push(kind === "admin" ? "/admin" : "/dashboard");
      } else {
        setError((res.data as Record<string, string>).error || "Login failed");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <Link href="/" className="mb-8 font-display text-xl font-bold tracking-wide">
        <span className="text-signal-orange">ARC</span>LINK
      </Link>

      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-8">
        <h1 className="font-display text-2xl font-bold">Sign In</h1>

        <div className="mt-4 flex gap-2">
          {(["user", "admin"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded px-3 py-1 text-sm capitalize ${
                kind === k ? "bg-signal-orange text-jet" : "bg-carbon text-soft-white/60"
              }`}
            >
              {k}
            </button>
          ))}
        </div>

        {error && <ErrorAlert message={error} className="mt-4" />}

        <form onSubmit={handleLogin} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm text-soft-white/60">Email</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-carbon px-3 py-2 text-soft-white outline-none focus:border-signal-orange"
              placeholder="you@company.com"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-signal-orange px-4 py-2 font-semibold text-jet transition hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Signing in..." : `Sign In as ${kind === "admin" ? "Admin" : "User"} →`}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-soft-white/30">
          No account?{" "}
          <Link href="/onboarding" className="text-signal-orange hover:underline">
            Start onboarding →
          </Link>
        </p>
      </div>
    </div>
  );
}

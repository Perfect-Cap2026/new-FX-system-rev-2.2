"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, setToken } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const res = mode === "login"
        ? await api<{ access_token: string }>("/auth/login", {
            method: "POST", body: new URLSearchParams({ username: email, password }),
          })
        : await api<{ access_token: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
      setToken(res.access_token);
      router.replace("/");
    } catch (err: any) {
      setError(err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm">
        <h1 className="text-3xl font-bold tracking-tight">FIP<span className="text-brass">.</span></h1>
        <p className="mb-8 mt-1 text-sm text-mist">
          {mode === "login" ? "Sign in to your analysis desk." : "Create your desk. Your default watchlist is set up for you."}
        </p>
        <label className="block text-sm text-mist" htmlFor="email">Email</label>
        <input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
          className="mb-4 mt-1 w-full border border-rule bg-deck px-3 py-2" />
        <label className="block text-sm text-mist" htmlFor="pw">Password</label>
        <input id="pw" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          className="mt-1 w-full border border-rule bg-deck px-3 py-2" />
        {mode === "register" && <p className="mt-1 text-xs text-mist">At least 8 characters.</p>}
        {error && <p className="mt-4 text-sm text-bear" role="alert">{error}</p>}
        <button disabled={busy} className="mt-6 w-full bg-brass py-2 font-semibold text-ink disabled:opacity-60">
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
          className="mt-4 w-full text-sm text-mist hover:text-paper">
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

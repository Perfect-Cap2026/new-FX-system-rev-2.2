"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Desk" },
  { href: "/macro", label: "Macro" },
  { href: "/intermarket", label: "Intermarket" },
  { href: "/markets", label: "Screener & heatmap" },
  { href: "/news", label: "News & calendar" },
  { href: "/journal", label: "Journal & risk" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [q, setQ] = useState("");
  const isLogin = path.startsWith("/login");

  useEffect(() => {
    if (!isLogin && !getToken()) router.replace("/login");
    else setReady(true);
  }, [isLogin, router]);

  if (isLogin) return <>{children}</>;
  if (!ready) return null;

  const go = (e: FormEvent) => {
    e.preventDefault();
    const s = q.trim().toUpperCase();
    if (s) router.push(`/asset/${encodeURIComponent(s)}`);
    setQ("");
  };

  return (
    <div className="min-h-screen md:grid md:grid-cols-[200px_1fr]">
      <aside className="border-b border-rule px-4 py-4 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <Link href="/" className="block text-lg font-bold tracking-tight">FIP<span className="text-brass">.</span></Link>
        <p className="mb-6 text-xs text-mist">Financial intelligence desk</p>
        <nav className="flex gap-4 overflow-x-auto text-sm md:flex-col md:gap-1">
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href}
                className={`whitespace-nowrap py-1 ${active ? "text-paper" : "text-mist hover:text-paper"}`}
                aria-current={active ? "page" : undefined}>
                {active && <span className="mr-2 inline-block h-2 w-2 bg-brass align-middle" aria-hidden />}{n.label}
              </Link>
            );
          })}
        </nav>
        <form onSubmit={go} className="mt-6">
          <label htmlFor="sym" className="text-xs text-mist">Analyse a symbol</label>
          <input id="sym" value={q} onChange={(e) => setQ(e.target.value)} placeholder="EURUSD=X, NVDA, GC=F"
            className="mt-1 w-full border border-rule bg-deck px-2 py-1.5 text-sm placeholder:text-mist/60" />
        </form>
        <button onClick={() => { setToken(null); router.replace("/login"); }}
          className="mt-6 hidden text-xs text-mist hover:text-paper md:block">Sign out</button>
      </aside>
      <main className="mx-auto w-full max-w-[1400px] px-4 py-6 md:px-8">{children}</main>
    </div>
  );
}

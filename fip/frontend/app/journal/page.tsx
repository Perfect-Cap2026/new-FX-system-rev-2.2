"use client";

import { FormEvent, useState } from "react";
import { ErrorNote, KV, Loading, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { price } from "@/lib/format";

const input = "w-full border border-rule bg-deck px-2 py-1.5 text-sm";

function RiskCalculator() {
  const [f, setF] = useState({ symbol: "EURUSD=X", entry: "", stop: "", targets: "", equity: "100000", risk_pct: "0.5" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });

  async function run(e: FormEvent) {
    e.preventDefault(); setErr(null);
    try {
      setRes(await api("/analysis/risk", { method: "POST", body: JSON.stringify({
        symbol: f.symbol, entry: +f.entry, stop: +f.stop, equity: +f.equity, risk_pct: +f.risk_pct,
        targets: f.targets.split(/[ ,]+/).filter(Boolean).map(Number) }) }));
    } catch (e: any) { setErr(e.message); setRes(null); }
  }

  return (
    <Panel title="Position size & prop-firm check">
      <form onSubmit={run} className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        {[["symbol", "Symbol"], ["entry", "Entry"], ["stop", "Stop"], ["targets", "Targets (comma separated)"], ["equity", "Account equity"], ["risk_pct", "Risk per trade %"]].map(([k, l]) => (
          <label key={k} className="text-mist">{l}<input required className={`${input} mt-1 text-paper`} value={(f as any)[k]} onChange={set(k)} inputMode={k === "symbol" ? "text" : "decimal"} /></label>
        ))}
        <button className="col-span-2 bg-brass py-2 font-semibold text-ink sm:col-span-3">Calculate size</button>
      </form>
      {err && <p className="mt-3 text-sm text-bear" role="alert">{err}</p>}
      {res && (
        <div className="mt-4">
          <KV k="Risk cash" v={res.position.risk_cash.toLocaleString()} />
          <KV k="Size" v={res.position.lots != null ? `${res.position.lots} lots` : res.position.contracts != null ? `${res.position.contracts} contracts` : `${res.position.units} units`} />
          <KV k="Leverage" v={`${res.position.leverage}x`} />
          <KV k="Reward:risk" v={res.setup.rr.map((r: number) => `${r}R`).join(" / ")} />
          <KV k="Grade" v={<span className={res.grade === "A+" ? "text-brass font-semibold" : ""}>{res.grade}</span>} />
          <ul className="mt-2 space-y-1 text-sm">{res.checks.map((c: any) => (
            <li key={c.check}><span className={c.pass ? "text-bull" : "text-bear"}>{c.pass ? "✓" : "✕"}</span> {c.check} <span className="text-mist">— {c.detail}</span></li>))}</ul>
          {res.position.note && <p className="mt-2 text-xs text-mist">{res.position.note}</p>}
        </div>
      )}
    </Panel>
  );
}

function Journal() {
  const { data, error, loading, reload } = useApi<any>("/journal");
  const [f, setF] = useState({ symbol: "", direction: "long", entry: "", stop: "", target: "", exit: "", setup_tag: "", notes: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });

  async function add(e: FormEvent) {
    e.preventDefault(); setErr(null);
    const num = (v: string) => (v ? +v : null);
    try {
      await api("/journal", { method: "POST", body: JSON.stringify({ ...f, entry: +f.entry, stop: +f.stop, target: num(f.target), exit: num(f.exit),
        setup_tag: f.setup_tag || null, notes: f.notes || null }) });
      setF({ ...f, entry: "", stop: "", target: "", exit: "", notes: "" });
      reload();
    } catch (e: any) { setErr(e.message); }
  }
  async function close(id: number) {
    const v = prompt("Exit price");
    if (!v) return;
    try { await api(`/journal/${id}/close?exit=${encodeURIComponent(v)}`, { method: "PATCH" }); reload(); } catch (e: any) { setErr(e.message); }
  }

  const s = data?.stats;
  return (
    <Panel title="Trade journal" aside={s ? `${s.closed} closed · win rate ${s.win_rate != null ? (s.win_rate * 100).toFixed(0) + "%" : "—"} · avg ${s.avg_r ?? "—"}R · total ${s.total_r}R` : undefined}>
      <form onSubmit={add} className="grid grid-cols-2 gap-2 text-sm md:grid-cols-8">
        <input required placeholder="Symbol" className={input} value={f.symbol} onChange={set("symbol")} aria-label="Symbol" />
        <select className={input} value={f.direction} onChange={set("direction")} aria-label="Direction"><option>long</option><option>short</option></select>
        <input required placeholder="Entry" className={input} value={f.entry} onChange={set("entry")} inputMode="decimal" aria-label="Entry" />
        <input required placeholder="Stop" className={input} value={f.stop} onChange={set("stop")} inputMode="decimal" aria-label="Stop" />
        <input placeholder="Target" className={input} value={f.target} onChange={set("target")} inputMode="decimal" aria-label="Target" />
        <input placeholder="Exit (if closed)" className={input} value={f.exit} onChange={set("exit")} inputMode="decimal" aria-label="Exit" />
        <input placeholder="Setup tag" className={input} value={f.setup_tag} onChange={set("setup_tag")} aria-label="Setup tag" />
        <button className="bg-brass font-semibold text-ink">Log trade</button>
        <textarea placeholder="Notes: why you took it, what you saw" className={`${input} col-span-2 md:col-span-8`} rows={2} value={f.notes} onChange={set("notes")} aria-label="Notes" />
      </form>
      {err && <p className="mt-2 text-sm text-bear" role="alert">{err}</p>}
      {loading && !data ? <Loading what="journal" /> : error ? <ErrorNote message={error} onRetry={reload} /> : (
        data.entries.length === 0 ? <p className="mt-4 text-sm text-mist">No trades logged yet. Log your first one above to start tracking R-multiples.</p> : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm num">
              <thead className="text-xs text-mist"><tr className="border-b border-rule text-left">
                <th className="py-1 font-normal">Opened</th><th className="font-normal">Symbol</th><th className="font-normal">Side</th>
                <th className="text-right font-normal">Entry</th><th className="text-right font-normal">Stop</th><th className="text-right font-normal">Exit</th>
                <th className="text-right font-normal">R</th><th className="pl-4 font-normal">Setup</th><th /></tr></thead>
              <tbody>{data.entries.map((j: any) => (
                <tr key={j.id} className="border-b border-rule/40">
                  <td className="py-1.5 text-mist">{new Date(j.opened_at).toLocaleDateString()}</td><td>{j.symbol}</td>
                  <td className={j.direction === "long" ? "text-bull" : "text-bear"}>{j.direction}</td>
                  <td className="text-right">{price(j.entry)}</td><td className="text-right">{price(j.stop)}</td><td className="text-right">{price(j.exit)}</td>
                  <td className={`text-right ${j.r_multiple > 0 ? "text-bull" : j.r_multiple < 0 ? "text-bear" : ""}`}>{j.r_multiple ?? "open"}</td>
                  <td className="pl-4 text-mist">{j.setup_tag}</td>
                  <td className="text-right">{j.exit == null && <button onClick={() => close(j.id)} className="text-brass underline underline-offset-4">Close</button>}</td>
                </tr>))}</tbody>
            </table>
          </div>))}
    </Panel>
  );
}

function Alerts() {
  const { data, error, loading, reload } = useApi<any[]>("/alerts");
  const [f, setF] = useState({ symbol: "", condition: "above", level: "", note: "" });
  const [err, setErr] = useState<string | null>(null);
  async function add(e: FormEvent) {
    e.preventDefault(); setErr(null);
    try { await api("/alerts", { method: "POST", body: JSON.stringify({ ...f, level: +f.level, note: f.note || null }) }); setF({ ...f, level: "", note: "" }); reload(); }
    catch (e: any) { setErr(e.message); }
  }
  async function del(id: number) { await api(`/alerts/${id}`, { method: "DELETE" }); reload(); }
  return (
    <Panel title="Price alerts" aside="checked against the latest daily close each time you open this page">
      <form onSubmit={add} className="grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
        <input required placeholder="Symbol" className={input} value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })} aria-label="Symbol" />
        <select className={input} value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })} aria-label="Condition"><option>above</option><option>below</option></select>
        <input required placeholder="Level" className={input} value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })} inputMode="decimal" aria-label="Level" />
        <input placeholder="Note" className={input} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} aria-label="Note" />
        <button className="bg-brass font-semibold text-ink">Add alert</button>
      </form>
      {err && <p className="mt-2 text-sm text-bear" role="alert">{err}</p>}
      {loading && !data ? <Loading what="alerts" /> : error ? <ErrorNote message={error} onRetry={reload} /> : (
        <ul className="mt-4 divide-y divide-rule/40 text-sm">
          {data!.length === 0 && <li className="py-2 text-mist">No alerts set.</li>}
          {data!.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-2 num">
              <span>{a.symbol} {a.condition} {price(a.level)} {a.note && <span className="text-mist">— {a.note}</span>}</span>
              <span className="flex gap-4">
                {a.triggered_at ? <span className="text-brass">Triggered {new Date(a.triggered_at).toLocaleString()}</span> : <span className="text-mist">now {price(a.price)}</span>}
                <button onClick={() => del(a.id)} className="text-mist hover:text-bear">Delete</button>
              </span>
            </li>))}
        </ul>)}
    </Panel>
  );
}

export default function JournalPage() {
  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold tracking-tight">Journal & risk</h1>
      <div className="grid gap-10 xl:grid-cols-2"><RiskCalculator /><Alerts /></div>
      <Journal />
    </div>
  );
}

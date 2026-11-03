"use client";

import { ErrorNote, KV, Loading, Panel } from "@/components/ui";
import { useApi } from "@/lib/api";
import { pct, price, tone } from "@/lib/format";

function cellColor(v: number | null) {
  if (v == null) return "transparent";
  const a = Math.min(1, Math.abs(v));
  return v >= 0 ? `rgba(63,179,155,${a * 0.85})` : `rgba(224,112,95,${a * 0.85})`;
}

export default function Intermarket() {
  const { data: d, error, loading, reload } = useApi<any>("/intermarket");
  if (loading && !d) return <Loading what="the cross-asset basket" />;
  if (error) return <ErrorNote message={error} onRetry={reload} />;
  if (!d || !d.correlation_matrix) return <ErrorNote message="Intermarket data is unavailable. Check the data provider and try again." onRetry={reload} />;
  const cm = d.correlation_matrix;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Intermarket</h1>
        <p className="text-sm text-mist">Regime: <span className="text-paper">{d.regime.label}</span> — {d.regime.notes.join(", ")}</p>
      </header>

      <Panel title="Correlation matrix" aside={`${d.window}-day daily returns (yields and VIX as changes)`}>
        <div className="overflow-x-auto">
          <table className="text-xs num">
            <thead><tr><th />{cm.assets.map((a: string) => <th key={a} className="h-24 w-16 align-bottom font-normal text-mist"><span className="inline-block -rotate-45 whitespace-nowrap">{a}</span></th>)}</tr></thead>
            <tbody>
              {cm.assets.map((row: string, i: number) => (
                <tr key={row}>
                  <th className="whitespace-nowrap pr-3 text-right font-normal text-mist">{row}</th>
                  {cm.values[i].map((v: number | null, j: number) => (
                    <td key={j} className="h-10 w-16 border border-ink text-center" style={{ background: i === j ? "#1A2C3A" : cellColor(v) }}
                      title={`${row} / ${cm.assets[j]}: ${v?.toFixed(2)}`}>{i === j ? "" : v?.toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-10 lg:grid-cols-3">
        <Panel title="Lead / lag vs S&P 500" aside="cross-correlation, ±5 days, 120d">
          {d.lead_lag.map((l: any) => <KV key={l.asset} k={l.asset} v={<span>{l.reading} <span className={tone(l.rho * 100, 25)}>ρ {l.rho.toFixed(2)}</span></span>} />)}
        </Panel>
        <Panel title="What drives the S&P 500" aside="single-factor R², 60d">
          {d.drivers.map((x: any) => (
            <div key={x.asset} className="flex items-center gap-3 py-1 text-sm">
              <span className="w-24 text-mist">{x.asset}</span>
              <div className="h-2 flex-1 bg-deck"><div className={`h-2 ${x.rho >= 0 ? "bg-bull" : "bg-bear"}`} style={{ width: `${x.r2 * 100}%` }} /></div>
              <span className="num w-12 text-right">{(x.r2 * 100).toFixed(0)}%</span>
            </div>))}
          <p className="mt-3 text-xs text-mist">Common factor (PC1) explains {(d.pc1.explained * 100).toFixed(0)}% of basket variance.</p>
        </Panel>
        <Panel title="Performance">
          <table className="w-full text-sm num">
            <thead className="text-xs text-mist"><tr className="text-left"><th className="font-normal">Asset</th><th className="text-right font-normal">Last</th><th className="text-right font-normal">1d</th><th className="text-right font-normal">1m</th></tr></thead>
            <tbody>{Object.entries(d.performance).map(([k, p]: any) => (
              <tr key={k} className="border-b border-rule/40"><td className="py-1">{k}</td><td className="text-right">{price(p.last)}</td>
                <td className={`text-right ${tone(p.chg_1d, 1e-9)}`}>{pct(p.chg_1d)}</td><td className={`text-right ${tone(p.chg_1m, 1e-9)}`}>{pct(p.chg_1m)}</td></tr>))}</tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

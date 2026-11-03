"use client";

import Link from "next/link";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MiniStrip } from "@/components/ConvictionStrip";
import { ErrorNote, KV, Loading, Panel } from "@/components/ui";
import { useApi } from "@/lib/api";
import { MODULE_NAMES, pct, price, signed, tone } from "@/lib/format";

export default function Desk() {
  const { data: d, error, loading, reload } = useApi<any>("/dashboard");
  if (loading && !d) return <Loading what="the desk — first load analyses the whole watchlist and can take a minute" />;
  if (error) return <ErrorNote message={error} onRetry={reload} />;
  if (!d) return null;
  const r = d.risk;

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Desk</h1>
          <p className="text-sm text-mist">Updated {new Date(d.generated_at).toLocaleString()}</p>
        </div>
        <button onClick={reload} className="border border-rule px-3 py-1.5 text-sm hover:border-brass">Refresh</button>
      </header>

      <div className="grid gap-10 lg:grid-cols-[1.6fr_1fr]">
        <Panel title="Executive summary">
          <ul className="max-w-[70ch] space-y-2 text-[15px] leading-relaxed">
            {d.executive_summary.map((s: string, i: number) => <li key={i}>{s}</li>)}
          </ul>
        </Panel>
        <Panel title="Risk assessment" aside={r.regime}>
          <KV k="VIX" v={r.vix?.toFixed(1) ?? "—"} />
          <KV k="Recession model (12m)" v={r.recession_probability != null ? `${(r.recession_probability * 100).toFixed(0)}%` : "—"} />
          <KV k="Fed net liquidity score" v={r.liquidity_score ?? "—"} />
          <KV k="HY credit spread" v={r.hy_spread != null ? `${r.hy_spread.toFixed(2)}%` : "—"} />
          <KV k="10Y–3M curve" v={r.curve_10y_3m != null ? `${r.curve_10y_3m.toFixed(2)}pp` : "—"} />
          {r.warnings.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-bear">{r.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>
          )}
        </Panel>
      </div>

      <Panel title="Asset rankings" aside="sorted by conviction = |composite| × confidence">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="text-left text-xs text-mist">
              <tr className="border-b border-rule">
                <th className="py-2 font-normal">Asset</th><th className="font-normal text-right">Price</th>
                <th className="font-normal text-right">1d</th><th className="pl-6 font-normal">Composite</th>
                <th className="font-normal text-right">Conf.</th><th className="pl-4 font-normal">Action</th>
                <th className="font-normal">Risk grade</th>
                {Object.values(MODULE_NAMES).map((m) => <th key={m} className="font-normal text-right">{m.slice(0, 5)}</th>)}
              </tr>
            </thead>
            <tbody>
              {d.rankings.map((row: any) => (
                <tr key={row.symbol} className="border-b border-rule/50 hover:bg-deck">
                  <td className="py-2">
                    <Link href={`/asset/${encodeURIComponent(row.symbol)}`} className="font-medium hover:text-brass">{row.symbol}</Link>
                    <div className="text-xs text-mist">{row.name !== row.symbol ? row.name : row.asset_class}</div>
                  </td>
                  <td className="num text-right">{price(row.price)}</td>
                  <td className={`num text-right ${tone(row.change_1d, 0.000001)}`}>{pct(row.change_1d)}</td>
                  <td className="pl-6"><div className="flex items-center gap-3"><MiniStrip value={row.composite} />
                    <span className={`num ${tone(row.composite)}`}>{signed(row.composite)}</span></div></td>
                  <td className="num text-right">{(row.confidence * 100).toFixed(0)}%</td>
                  <td className="pl-4">{row.action}</td>
                  <td className={row.grade === "A+" ? "text-brass font-semibold" : "text-mist"}>{row.grade}</td>
                  {Object.keys(MODULE_NAMES).map((k) => (
                    <td key={k} className={`num text-right ${tone(row.modules[k])}`}>{row.modules[k] == null ? "n/a" : signed(row.modules[k])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-10 lg:grid-cols-2">
        <Panel title="Trade opportunities" aside="composite clears ±35 with confidence ≥ 55%">
          {d.opportunities.length === 0 && <p className="text-sm text-mist">Nothing clears the threshold right now. Standing aside is a position.</p>}
          <ul className="divide-y divide-rule/50">
            {d.opportunities.map((o: any) => (
              <li key={o.symbol} className="py-3 text-sm">
                <div className="flex justify-between">
                  <Link href={`/asset/${encodeURIComponent(o.symbol)}`} className="font-medium hover:text-brass">{o.symbol}</Link>
                  <span className={tone(o.composite)}>{o.action} · grade {o.grade}</span>
                </div>
                {o.setup && (
                  <p className="num mt-1 text-mist">
                    Entry <span className="text-brass">{price(o.setup.entry)}</span> · stop {price(o.setup.stop)} · targets{" "}
                    {o.setup.targets.map(price).join(" / ")} · {o.setup.rr.join("R / ")}R
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Portfolio suggestions" aside="conviction-weighted, max 35% each, skips >0.75 correlated duplicates">
          {d.portfolio.length === 0 ? <p className="text-sm text-mist">No positions meet the lean threshold.</p> : (
            <ul className="space-y-2 text-sm">
              {d.portfolio.map((p: any) => (
                <li key={p.symbol} className="flex items-center gap-3">
                  <span className="w-24 font-medium">{p.symbol}</span>
                  <span className={`w-12 ${p.direction === "long" ? "text-bull" : "text-bear"}`}>{p.direction}</span>
                  <div className="h-2 flex-1 bg-deck"><div className={`h-2 ${p.direction === "long" ? "bg-bull" : "bg-bear"}`} style={{ width: `${p.weight * 100}%` }} /></div>
                  <span className="num w-12 text-right">{(p.weight * 100).toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-mist">Model allocation for research. Size real positions with the risk calculator.</p>
        </Panel>
      </div>

      <div className="grid gap-10 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Sector opportunities" aside={d.sectors.phase ? `leadership: ${d.sectors.phase}` : undefined}>
          {d.sectors.rankings.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={d.sectors.rankings} layout="vertical" margin={{ left: 20, right: 20 }}>
                  <XAxis type="number" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} stroke="#93A7B4" fontSize={11} />
                  <YAxis type="category" dataKey="sector" width={130} stroke="#93A7B4" fontSize={12} />
                  <Tooltip cursor={{ fill: "#1A2C3A" }} contentStyle={{ background: "#1A2C3A", border: "1px solid #2B4354" }}
                    formatter={(v: number) => [`${(v * 100).toFixed(2)}%`, "RS score vs SPY"]} />
                  <Bar dataKey="score">
                    {d.sectors.rankings.map((s: any) => <Cell key={s.symbol} fill={s.score >= 0 ? "#3FB39B" : "#E0705F"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="text-sm text-mist">Sector data unavailable.</p>}
        </Panel>
        <Panel title="Macro outlook">
          <KV k="Regime" v={d.macro.regime ?? "—"} />
          <KV k="Inflation" v={d.macro.inflation?.direction ?? "—"} />
          <KV k="Growth" v={d.macro.growth?.label ?? "—"} />
          <KV k="Fed funds" v={d.macro.rates?.["Fed funds"]?.toFixed(2) ?? "—"} />
          <KV k="10Y real yield" v={d.macro.rates?.["10Y real yield"]?.toFixed(2) ?? "—"} />
          <KV k="Data surprise score" v={d.macro.market_impact_score ?? "—"} />
          <Link href="/macro" className="mt-3 inline-block text-sm text-brass underline underline-offset-4">Open macro engine</Link>
        </Panel>
      </div>

      <div className="grid gap-10 lg:grid-cols-2">
        <Panel title="Geopolitical risk headlines" aside="flagged from watchlist news">
          {d.geopolitical.length === 0 ? <p className="text-sm text-mist">No geopolitical terms in current headlines.</p> : (
            <ul className="space-y-2 text-sm">{d.geopolitical.map((g: any) => (
              <li key={g.title}>{g.title} <span className="text-xs text-brass">{g.terms.join(", ")}</span></li>))}</ul>
          )}
        </Panel>
        <Panel title="Central banks" aside={d.central_banks?.as_of ? `table as of ${d.central_banks.as_of}` : undefined}>
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(d.central_banks?.banks ?? {}).map(([ccy, b]: any) => (
                <tr key={ccy} className="border-b border-rule/40">
                  <td className="py-1.5 w-12 font-medium">{ccy}</td><td className="text-mist">{b.bank}</td>
                  <td className="num text-right">{b.rate.toFixed(2)}%</td>
                  <td className={`pl-4 ${b.bias.includes("hik") || b.bias.includes("hawk") ? "text-brass" : "text-mist"}`}>{b.bias}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

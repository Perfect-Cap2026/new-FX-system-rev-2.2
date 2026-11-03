"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import TradingViewWidget from "@/components/TradingViewWidget";
import { ErrorNote, KV, Loading, Panel } from "@/components/ui";
import { useApi } from "@/lib/api";

const f2 = (x?: number | null, s = "") => (x == null ? "—" : `${x.toFixed(2)}${s}`);

export default function Macro() {
  const { data: m, error, loading, reload } = useApi<any>("/macro/dashboard");
  if (loading && !m) return <Loading what="macro data from FRED" />;
  if (error) return <ErrorNote message={error} onRetry={reload} />;
  if (!m) return null;
  const rp = m.recession_probability;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Macro engine</h1>
        <p className="max-w-[70ch] text-sm text-mist">US data from FRED; FX policy rates from the central-bank table. Regime: <span className="text-paper">{m.regime}</span>.</p>
      </header>

      <div className="grid gap-10 md:grid-cols-2 xl:grid-cols-4">
        <Panel title="Inflation" aside={m.inflation.direction}>
          {Object.entries(m.inflation.series).map(([k, v]: any) => (
            <KV key={k} k={k} v={`${f2(v.yoy, "%")} yoy · ${f2(v.ann_3m, "%")} 3m ann.`} />))}
          <p className="mt-2 text-xs text-mist">Direction compares 3-month annualised pace with the 12-month rate.</p>
        </Panel>
        <Panel title="Growth & labour" aside={m.growth.label}>
          {Object.entries(m.growth.indicators).map(([k, v]: any) => (
            <KV key={k} k={k.replace(/_/g, " ")} v={typeof v === "number" ? v.toFixed(2) : String(v)} />))}
        </Panel>
        <Panel title="Rates & curve">
          {Object.entries(m.rates).map(([k, v]: any) => <KV key={k} k={k.replace(/_/g, " ")} v={f2(v)} />)}
        </Panel>
        <Panel title="Recession probability" aside="model estimate, 12 months">
          {rp ? <>
            <p className="num text-4xl font-bold">{(rp.value * 100).toFixed(0)}%</p>
            {Object.entries(rp.components).map(([k, v]: any) => <KV key={k} k={k.replace(/_/g, " ")} v={`${(v * 100).toFixed(0)}%`} />)}
            <p className="mt-2 text-xs text-mist">{rp.note}</p>
          </> : <p className="text-sm text-mist">Unavailable.</p>}
        </Panel>
      </div>

      <div className="grid gap-10 lg:grid-cols-[1.6fr_1fr]">
        <Panel title="Fed net liquidity" aside={m.liquidity ? `score ${m.liquidity.score}/100 · 13w Δ ${m.liquidity.change_13w_bn.toLocaleString()}bn` : undefined}>
          {m.liquidity?.series ? (
            <div className="h-64">
              <ResponsiveContainer>
                <AreaChart data={m.liquidity.series}>
                  <CartesianGrid stroke="#2B4354" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="t" stroke="#93A7B4" fontSize={11} minTickGap={60} />
                  <YAxis stroke="#93A7B4" fontSize={11} domain={["auto", "auto"]} tickFormatter={(v) => `${(v / 1000).toFixed(1)}T`} />
                  <Tooltip contentStyle={{ background: "#1A2C3A", border: "1px solid #2B4354" }} formatter={(v: number) => [`$${v.toLocaleString()}bn`, "Net liquidity"]} />
                  <Area dataKey="v" stroke="#CFA85A" fill="#CFA85A" fillOpacity={0.12} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="text-sm text-mist">Liquidity series unavailable.</p>}
          <p className="mt-2 text-xs text-mist">Fed balance sheet − Treasury General Account − reverse repo. A US proxy for global liquidity.</p>
        </Panel>
        <Panel title="Latest data vs trend" aside={m.market_impact_score != null ? `impact score ${m.market_impact_score}/100` : undefined}>
          {m.data_surprises.map((s: any) => (
            <div key={s.indicator} className="flex items-center gap-3 py-1 text-sm">
              <span className="w-40 text-mist">{s.indicator}</span>
              <div className="relative h-2 flex-1 bg-deck">
                <div className="absolute inset-y-0 left-1/2 w-px bg-rule" />
                <div className={`absolute inset-y-0 ${s.z >= 0 ? "bg-bull" : "bg-bear"}`}
                  style={{ left: s.z >= 0 ? "50%" : `${50 + Math.max(-3, s.z) / 6 * 100}%`, width: `${Math.min(3, Math.abs(s.z)) / 6 * 100}%` }} />
              </div>
              <span className="num w-14 text-right">{s.z > 0 ? "+" : ""}{s.z.toFixed(1)}σ</span>
            </div>
          ))}
          <p className="mt-2 text-xs text-mist">Latest change vs the prior 12 changes. Consensus-based surprises need a calendar feed.</p>
        </Panel>
      </div>

      <Panel title="Economic calendar" aside="TradingView, high and medium importance">
        <TradingViewWidget widget="events" height={560}
          config={{ importanceFilter: "0,1", countryFilter: "us,eu,gb,jp,ch,au,ca,nz,cn" }} />
      </Panel>
    </div>
  );
}

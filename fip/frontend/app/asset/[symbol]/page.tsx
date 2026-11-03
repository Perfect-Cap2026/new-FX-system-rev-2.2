"use client";

import { use } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ConvictionStrip } from "@/components/ConvictionStrip";
import TradingViewWidget from "@/components/TradingViewWidget";
import { Bias, ErrorNote, KV, Loading, Panel } from "@/components/ui";
import { useApi } from "@/lib/api";
import { MODULE_NAMES, pct, price, signed, tone, tvSymbol } from "@/lib/format";

const ORDER = ["macro", "fundamental", "institutional", "technical", "sentiment", "intermarket"];

export default function Asset({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = decodeURIComponent(raw);
  const { data: a, error, loading, reload } = useApi<any>(`/analysis/${encodeURIComponent(symbol)}`);
  if (loading && !a) return <Loading what={`analysis for ${symbol}`} />;
  if (error) return <ErrorNote message={error} onRetry={reload} />;
  if (!a) return null;

  const d = a.decision;
  const m = a.modules;
  const setup = a.trade_setup;
  const tech = m.technical.details;
  const inst = m.institutional.details;
  // Explicit y-domain so trade levels outside the recent price range are still drawn
  const yDomain = (() => {
    const vals = [...(tech?.series ?? []).map((p: any) => p.c), ...(setup ? [setup.entry, setup.stop, ...setup.targets] : [])];
    if (!vals.length) return ["auto", "auto"] as const;
    const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.04;
    return [lo - pad, hi + pad] as [number, number];
  })();

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="text-sm text-mist">{a.asset_class} · {symbol}</p>
          <h1 className="text-3xl font-bold tracking-tight">{a.name}</h1>
          <p className="num mt-1 text-lg">{price(a.price)} <span className={tone(a.change_1d, 1e-9)}>{pct(a.change_1d)}</span></p>
        </div>
        <div className="sm:text-right">
          <p className="text-sm text-mist">Recommended action</p>
          <p className={`text-2xl font-bold ${tone(d.composite, 35)}`}>{d.action}</p>
          <p className="text-sm"><Bias label={d.bias} /> · confidence <span className="num">{(d.confidence * 100).toFixed(0)}%</span> · risk grade{" "}
            <span className={a.risk.grade === "A+" ? "font-semibold text-brass" : ""}>{a.risk.grade}</span></p>
        </div>
      </header>

      <Panel title="Where every module sits" aside={`composite ${signed(d.composite)} · agreement ${(d.agreement * 100).toFixed(0)}% · coverage ${(d.coverage * 100).toFixed(0)}%`}>
        <ConvictionStrip composite={d.composite} contributions={d.contributions} />
        {d.missing?.length > 0 && <p className="mt-2 text-xs text-mist">Not scored for this asset: {d.missing.map((k: string) => MODULE_NAMES[k]).join(", ")}. Weights renormalised.</p>}
      </Panel>

      <Panel title="Investment thesis" aside={a.thesis_source === "template" ? "rule-based (add ANTHROPIC_API_KEY for Claude-written thesis)" : `written by ${a.thesis_source}`}>
        <p className="max-w-[75ch] whitespace-pre-line text-[15px] leading-relaxed">{a.thesis.replace(/\*\*/g, "")}</p>
      </Panel>

      <div className="grid gap-10 xl:grid-cols-[1.6fr_1fr]">
        <Panel title="Chart">
          <TradingViewWidget widget="advanced-chart" height={520}
            config={{ symbol: tvSymbol(symbol), interval: "D", timezone: "Etc/UTC", style: "1", allow_symbol_change: true,
                      studies: ["STD;RSI", "STD;MACD"], hide_side_toolbar: false }} />
        </Panel>
        <Panel title="Trade setup" aside={setup ? setup.entry_type : undefined}>
          {!setup ? <p className="text-sm text-mist">No directional setup: technical bias is inside the ±15 dead zone.</p> : (
            <>
              <KV k="Direction" v={<span className={setup.direction === "long" ? "text-bull" : "text-bear"}>{setup.direction}</span>} />
              <KV k="Entry" v={<span className="text-brass">{price(setup.entry)}</span>} />
              <KV k="Stop" v={price(setup.stop)} />
              {setup.targets.map((t: number, i: number) => <KV key={i} k={`Target ${i + 1}`} v={`${price(t)} (${setup.rr[i]}R)`} />)}
              <KV k="Stop basis" v={setup.stop_basis} />
              {a.risk.position && <>
                <KV k="Risk cash" v={a.risk.position.risk_cash?.toLocaleString()} className="mt-3 border-t border-rule pt-2" />
                <KV k="Size" v={a.risk.position.lots != null ? `${a.risk.position.lots} lots` : a.risk.position.contracts != null ? `${a.risk.position.contracts} contracts` : `${a.risk.position.units} units`} />
                <KV k="Leverage" v={`${a.risk.position.leverage}x`} />
              </>}
            </>
          )}
          <h3 className="mb-1 mt-5 text-sm font-semibold">A+ risk gate</h3>
          <ul className="space-y-1 text-sm">
            {a.risk.checks.map((c: any) => (
              <li key={c.check} className="flex gap-2"><span className={c.pass ? "text-bull" : "text-bear"} aria-label={c.pass ? "pass" : "fail"}>{c.pass ? "✓" : "✕"}</span>
                <span>{c.check} <span className="text-mist">— {c.detail}</span></span></li>
            ))}
          </ul>
        </Panel>
      </div>

      {tech?.series && (
        <Panel title="Levels map" aside="daily close with S/R, Fibonacci, volume POC and trade levels">
          <div className="h-80">
            <ResponsiveContainer>
              <LineChart data={tech.series} margin={{ right: 70 }}>
                <CartesianGrid stroke="#2B4354" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="t" stroke="#93A7B4" fontSize={11} minTickGap={50} />
                <YAxis domain={yDomain as any} allowDataOverflow stroke="#93A7B4" fontSize={11} width={70} tickFormatter={(v) => price(v)} />
                <Tooltip contentStyle={{ background: "#1A2C3A", border: "1px solid #2B4354" }} formatter={(v: number) => price(v)} />
                {tech.volume_profile?.val && <ReferenceArea y1={tech.volume_profile.val} y2={tech.volume_profile.vah} fill="#93A7B4" fillOpacity={0.06} />}
                {tech.levels.map((l: any) => <ReferenceLine key={l.price} y={l.price} stroke={l.type === "support" ? "#3FB39B" : "#E0705F"} strokeOpacity={0.5} strokeDasharray="4 4" />)}
                {tech.volume_profile?.poc && <ReferenceLine y={tech.volume_profile.poc} stroke="#93A7B4" label={{ value: "POC", fill: "#93A7B4", fontSize: 10, position: "right" }} />}
                {/* Recharts ignores children wrapped in fragments, so pass an array */}
                {setup && [
                  <ReferenceLine key="entry" y={setup.entry} stroke="#CFA85A" strokeWidth={2} label={{ value: "entry", fill: "#CFA85A", fontSize: 11, position: "right" }} />,
                  <ReferenceLine key="stop" y={setup.stop} stroke="#E0705F" strokeWidth={2} label={{ value: "stop", fill: "#E0705F", fontSize: 11, position: "right" }} />,
                  ...setup.targets.map((t: number, i: number) => <ReferenceLine key={`t${i}`} y={t} stroke="#3FB39B" label={{ value: `T${i + 1}`, fill: "#3FB39B", fontSize: 11, position: "right" }} />),
                ]}
                <Line dataKey="c" dot={false} stroke="#ECE7DA" strokeWidth={1.5} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      <div className="grid gap-10 lg:grid-cols-2 2xl:grid-cols-3">
        {ORDER.map((k) => <ModuleCard key={k} name={k} mod={m[k]} />)}
      </div>

      {m.institutional.available && (
        <div className="grid gap-10 lg:grid-cols-3">
          <Panel title="Structure & liquidity" aside={`state: ${inst.structure_state}`}>
            <ul className="space-y-1 text-sm">{inst.events.map((e: any, i: number) => (
              <li key={i} className="num"><span className="text-mist">{e.t}</span> <span className={e.dir === "bullish" ? "text-bull" : "text-bear"}>{e.kind} {e.dir}</span> @ {price(e.level)}</li>))}</ul>
            <KV k="Buy-side (nearest swing high)" v={price(inst.liquidity.buy_side.nearest_swing_high)} className="mt-3" />
            <KV k="Equal highs" v={inst.liquidity.buy_side.equal_highs.map(price).join(", ") || "—"} />
            <KV k="Sell-side (nearest swing low)" v={price(inst.liquidity.sell_side.nearest_swing_low)} />
            <KV k="Equal lows" v={inst.liquidity.sell_side.equal_lows.map(price).join(", ") || "—"} />
            <KV k="Zone" v={`${inst.premium_discount.zone} (${(inst.premium_discount.position * 100).toFixed(0)}%)`} />
          </Panel>
          <Panel title="Imbalances" aside="unmitigated">
            <ul className="space-y-1 text-sm num">
              {[...inst.fair_value_gaps.map((g: any) => ({ ...g, kind: "FVG", lo: g.bottom, hi: g.top })),
                ...inst.order_blocks.map((o: any) => ({ ...o, kind: "OB", lo: o.low, hi: o.high }))].map((z: any, i: number) => (
                <li key={i}><span className={z.dir === "bullish" ? "text-bull" : "text-bear"}>{z.dir} {z.kind}</span> <span className="text-mist">{z.t}</span> {price(z.lo)}–{price(z.hi)}</li>))}
              {inst.fair_value_gaps.length + inst.order_blocks.length === 0 && <li className="text-mist">None open.</li>}
            </ul>
            {inst.sweeps.length > 0 && <><h3 className="mb-1 mt-4 text-sm font-semibold">Recent sweeps</h3>
              <ul className="space-y-1 text-sm">{inst.sweeps.map((s: any, i: number) => <li key={i}><span className="text-mist">{s.t}</span> {s.note}</li>)}</ul></>}
          </Panel>
          <Panel title="Probability matrix" aside={inst.probability_matrix?.horizon_bars ? `${inst.probability_matrix.horizon_bars}-bar forward, this series` : undefined}>
            {inst.probability_matrix?.base_rate_up != null ? <>
              <KV k="Base rate (up)" v={`${(inst.probability_matrix.base_rate_up * 100).toFixed(0)}%`} />
              {["bullish_structure", "bearish_structure"].map((s) => inst.probability_matrix[s] && (
                <KV key={s} k={`After ${s.replace("_", " ")}`} v={`${(inst.probability_matrix[s].p_up * 100).toFixed(0)}% up · n=${inst.probability_matrix[s].n}`} />))}
              <p className="mt-2 text-xs text-mist">Counted from this instrument's own history; not a forecast guarantee.</p>
            </> : <p className="text-sm text-mist">Not enough history.</p>}
          </Panel>
        </div>
      )}

      <div className="grid gap-10 lg:grid-cols-2">
        {m.fundamental.available && m.fundamental.details.scenarios && (
          <Panel title="Bull · base · bear" aside={m.fundamental.details.scenarios.horizon}>
            <div className="grid grid-cols-3 gap-4 text-sm">
              {(["bull", "base", "bear"] as const).map((c) => {
                const s = m.fundamental.details.scenarios[c];
                return (
                  <div key={c} className={`border-t-2 pt-2 ${c === "bull" ? "border-bull" : c === "bear" ? "border-bear" : "border-mist"}`}>
                    <p className="font-semibold capitalize">{c} case</p>
                    <p className="num text-lg">{price(s.target)}</p>
                    <p className="num text-xs text-mist">{(s.probability * 100).toFixed(0)}% weight</p>
                    <ul className="mt-2 space-y-0.5 text-xs text-mist">{s.drivers.map((x: string) => <li key={x}>{x}</li>)}</ul>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-xs text-mist">{m.fundamental.details.scenarios.note}</p>
          </Panel>
        )}
        {m.technical.available && (
          <Panel title="Multi-timeframe">
            <table className="w-full text-sm num">
              <thead className="text-xs text-mist"><tr className="border-b border-rule text-left">
                <th className="py-1 font-normal">TF</th><th className="font-normal">Structure</th><th className="font-normal text-right">Score</th>
                <th className="font-normal text-right">RSI</th><th className="font-normal text-right">ADX</th><th className="font-normal text-right">ATR</th></tr></thead>
              <tbody>{Object.entries(tech.timeframes).map(([tf, v]: any) => (
                <tr key={tf} className="border-b border-rule/40"><td className="py-1.5">{tf}</td><td>{v.structure}</td>
                  <td className={`text-right ${tone(v.score)}`}>{signed(v.score)}</td><td className="text-right">{v.rsi}</td>
                  <td className="text-right">{v.adx}</td><td className="text-right">{price(v.atr)}</td></tr>))}</tbody>
            </table>
            <KV k="20-day VWAP" v={price(tech.vwap_20d)} className="mt-3" />
            <KV k="Value area" v={tech.volume_profile?.val ? `${price(tech.volume_profile.val)} – ${price(tech.volume_profile.vah)}` : "n/a (no volume)"} />
            <KV k={`Fibonacci (${tech.fibonacci.direction} leg)`} v={Object.entries(tech.fibonacci.levels).map(([r, p]: any) => `${r}: ${price(p)}`).join("  ")} />
          </Panel>
        )}
      </div>

      {m.sentiment.available && m.sentiment.details.headlines?.length > 0 && (
        <Panel title="News intelligence" aside={m.sentiment.label}>
          <ul className="divide-y divide-rule/40 text-sm">
            {m.sentiment.details.headlines.map((h: any, i: number) => (
              <li key={i} className="flex gap-4 py-2">
                <span className={`num w-12 shrink-0 text-right ${tone(h.sentiment * 100)}`}>{signed(h.sentiment, 2)}</span>
                <span>{h.url ? <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-brass">{h.title}</a> : h.title}
                  {h.publisher && <span className="ml-2 text-xs text-mist">{h.publisher}</span>}</span>
              </li>))}
          </ul>
        </Panel>
      )}

      <p className="text-xs text-mist">{a.disclaimer} Data: {a.data_provider}, bar as of {new Date(a.as_of).toLocaleString()}.</p>
    </div>
  );
}

function ModuleCard({ name, mod }: { name: string; mod: any }) {
  return (
    <Panel title={MODULE_NAMES[name]} aside={mod.available ? <span><Bias label={mod.label} /> · <span className="num">{signed(mod.score)}</span> · conf {(mod.confidence * 100).toFixed(0)}%</span> : "not scored"}>
      {!mod.available ? <p className="text-sm text-mist">{mod.details?.reason}</p> : (
        <ul className="space-y-1.5 text-sm">
          {mod.signals.map((s: any, i: number) => (
            <li key={i} className="grid grid-cols-[1fr_auto] gap-x-3">
              <span>{s.name} <span className="text-mist">{String(s.value ?? "")}</span>
                {s.note && <span className="block text-xs text-mist/80">{s.note}</span>}</span>
              <span className={`num ${tone(s.impact, 3)}`}>{signed(s.impact, 1)}</span>
            </li>))}
        </ul>
      )}
    </Panel>
  );
}

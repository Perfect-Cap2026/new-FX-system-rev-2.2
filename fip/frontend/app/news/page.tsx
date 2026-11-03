"use client";

import TradingViewWidget from "@/components/TradingViewWidget";
import { Panel } from "@/components/ui";

export default function News() {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">News & calendar</h1>
        <p className="text-sm text-mist">Market-wide headlines and scheduled releases. Scored, per-asset headlines are on each asset page.</p>
      </header>
      <div className="grid gap-10 xl:grid-cols-2">
        <Panel title="Top stories">
          <TradingViewWidget widget="timeline" height={700} config={{ feedMode: "market", market: "forex", displayMode: "regular" }} />
        </Panel>
        <Panel title="Economic calendar" aside="high importance">
          <TradingViewWidget widget="events" height={700} config={{ importanceFilter: "1", countryFilter: "us,eu,gb,jp,ch,au,ca,nz,cn,za" }} />
        </Panel>
      </div>
    </div>
  );
}

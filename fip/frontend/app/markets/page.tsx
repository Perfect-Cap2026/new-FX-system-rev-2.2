"use client";

import TradingViewWidget from "@/components/TradingViewWidget";
import { Panel } from "@/components/ui";

export default function Markets() {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Screener & heatmap</h1>
        <p className="text-sm text-mist">Live TradingView widgets. Open any symbol in the sidebar search to run the full FIP analysis on it.</p>
      </header>
      <Panel title="S&P 500 heatmap" aside="sized by market cap, coloured by daily change">
        <TradingViewWidget widget="stock-heatmap" height={560}
          config={{ dataSource: "SPX500", blockSize: "market_cap_basic", blockColor: "change", grouping: "sector", hasTopBar: true }} />
      </Panel>
      <div className="grid gap-10 xl:grid-cols-2">
        <Panel title="Stock screener">
          <TradingViewWidget widget="screener" height={560} config={{ defaultColumn: "overview", defaultScreen: "most_capitalized", market: "america" }} />
        </Panel>
        <Panel title="Forex cross rates">
          <TradingViewWidget widget="forex-cross-rates" height={560} config={{ currencies: ["EUR", "USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD"] }} />
        </Panel>
      </div>
    </div>
  );
}

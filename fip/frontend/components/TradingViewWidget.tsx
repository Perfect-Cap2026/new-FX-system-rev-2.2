"use client";

import { useEffect, useRef } from "react";

/**
 * Embeds an official TradingView widget (free, no key). `widget` is the script name, e.g.
 * "advanced-chart", "events", "stock-heatmap", "timeline", "screener".
 */
export default function TradingViewWidget({ widget, config, height = 520 }:
  { widget: string; config: Record<string, unknown>; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const cfg = JSON.stringify(config);

  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    host.innerHTML = '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>';
    const s = document.createElement("script");
    s.src = `https://s3.tradingview.com/external-embedding/embed-widget-${widget}.js`;
    s.async = true;
    s.type = "text/javascript";
    s.innerHTML = JSON.stringify({ colorTheme: "dark", isTransparent: true, locale: "en", width: "100%", height: "100%", ...JSON.parse(cfg) });
    host.appendChild(s);
    return () => { host.innerHTML = ""; };
  }, [widget, cfg]);

  return <div ref={ref} className="tradingview-widget-container w-full" style={{ height }} />;
}

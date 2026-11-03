export const pct = (x?: number | null, d = 2) =>
  x == null ? "—" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;

export const signed = (x?: number | null, d = 0) =>
  x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(d)}`;

export function price(x?: number | null) {
  if (x == null) return "—";
  const a = Math.abs(x);
  const d = a >= 1000 ? 2 : a >= 10 ? 2 : a >= 1 ? 4 : 5;
  return x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export const tone = (x?: number | null, dead = 15) =>
  x == null ? "text-mist" : x >= dead ? "text-bull" : x <= -dead ? "text-bear" : "text-mist";

export const MODULE_NAMES: Record<string, string> = {
  macro: "Macro",
  fundamental: "Fundamental",
  institutional: "Institutional",
  technical: "Technical",
  sentiment: "Sentiment",
  intermarket: "Intermarket",
};

/** TradingView symbol for a Yahoo-style ticker (for embedded widgets). */
export function tvSymbol(s: string): string {
  const map: Record<string, string> = {
    "GC=F": "COMEX:GC1!", "SI=F": "COMEX:SI1!", "CL=F": "NYMEX:CL1!", "NG=F": "NYMEX:NG1!", "HG=F": "COMEX:HG1!",
    "ES=F": "CME_MINI:ES1!", "NQ=F": "CME_MINI:NQ1!", "^GSPC": "SP:SPX", "^NDX": "NASDAQ:NDX", "^DJI": "DJ:DJI",
    "^VIX": "CBOE:VIX", "^TNX": "TVC:TNX", "DX-Y.NYB": "TVC:DXY", "BTC-USD": "BITSTAMP:BTCUSD", "ETH-USD": "BITSTAMP:ETHUSD",
  };
  if (map[s]) return map[s];
  if (s.endsWith("=X")) { const p = s.replace("=X", ""); return `FX:${p.length === 3 ? "USD" + p : p}`; }
  if (s.endsWith("-USD")) return `BINANCE:${s.replace("-USD", "")}USDT`;
  return s;
}

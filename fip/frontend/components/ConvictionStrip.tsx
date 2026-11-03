import { MODULE_NAMES, signed } from "@/lib/format";

type Contribution = { score: number; weight: number; label: string };

const x = (v: number) => `${((Math.max(-100, Math.min(100, v)) + 100) / 200) * 100}%`;

/**
 * The platform's signature read-out: one −100…+100 axis with every module placed on it,
 * the weighted composite as the heavy marker, and the ±35 conviction gates.
 */
export function ConvictionStrip({ composite, contributions, threshold = 35 }:
  { composite: number; contributions: Record<string, Contribution>; threshold?: number }) {
  const entries = Object.entries(contributions).sort((a, b) => a[1].score - b[1].score);
  const lastX = [-Infinity, -Infinity, -Infinity, -Infinity];
  const placed = entries.map(([k, c], i) => {
    const lane = [0, 2, 1, 3].find((l) => c.score - lastX[l] > 24) ?? i % 4;
    lastX[lane] = c.score;
    return { k, c, lane };
  });
  const color = composite >= threshold ? "#3FB39B" : composite <= -threshold ? "#E0705F" : "#ECE7DA";
  return (
    <figure aria-label={`Composite ${signed(composite)} on a scale from minus 100 to plus 100`}>
      <div className="relative h-36">
        {/* gates */}
        <div className="absolute inset-y-6 border-l border-dashed border-brass/60" style={{ left: x(-threshold) }} />
        <div className="absolute inset-y-6 border-l border-dashed border-brass/60" style={{ left: x(threshold) }} />
        <div className="absolute inset-y-8 left-1/2 border-l border-rule" />
        {/* axis */}
        <div className="absolute left-0 right-0 top-1/2 h-px bg-rule" />
        <div className="strip-in absolute top-1/2 h-[3px] -translate-y-1/2 origin-[50%]"
             style={{ left: x(Math.min(0, composite)), right: `calc(100% - ${x(Math.max(0, composite))})`, background: color }} />
        {/* modules: greedy lane assignment so close scores never overlap (2 lanes above, 2 below) */}
        {placed.map(({ k, c, lane }) => {
          const above = lane < 2;
          const top = ["0px", "18px", "calc(50% + 6px)", "calc(50% + 24px)"][lane];
          return (
            <div key={k} className="absolute hidden -translate-x-1/2 text-center sm:block" style={{ left: x(c.score), top }}>
              {!above && <div className="mx-auto h-2 w-px bg-mist/60" />}
              <div className="whitespace-nowrap text-[11px] leading-tight text-mist">
                {MODULE_NAMES[k] ?? k} <span className="num text-paper">{signed(c.score)}</span>
              </div>
              {above && <div className="mx-auto h-2 w-px bg-mist/60" />}
            </div>
          );
        })}
        {placed.map(({ k, c }) => (
          <div key={`t-${k}`} className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-mist sm:hidden" style={{ left: x(c.score) }} />
        ))}
        {/* composite marker */}
        <div className="absolute top-1/2 h-7 w-[3px] -translate-x-1/2 -translate-y-1/2" style={{ left: x(composite), background: color }} />
      </div>
      <ul className="mt-2 grid grid-cols-2 gap-x-6 text-xs sm:hidden">
        {entries.map(([k, c]) => <li key={k} className="flex justify-between"><span className="text-mist">{MODULE_NAMES[k] ?? k}</span><span className="num">{signed(c.score)}</span></li>)}
      </ul>
      <figcaption className="flex justify-between text-[11px] text-mist num">
        <span>−100 bearish</span><span>trade gate ±{threshold}</span><span>bullish +100</span>
      </figcaption>
    </figure>
  );
}

/** Compact strip for table rows. */
export function MiniStrip({ value }: { value: number }) {
  const c = value >= 35 ? "bg-bull" : value <= -35 ? "bg-bear" : value >= 15 ? "bg-bull/60" : value <= -15 ? "bg-bear/60" : "bg-mist/60";
  return (
    <div className="relative h-3 w-28" aria-hidden>
      <div className="absolute left-0 right-0 top-1/2 h-px bg-rule" />
      <div className="absolute inset-y-0 left-1/2 w-px bg-rule" />
      <div className={`absolute top-1/2 h-[3px] -translate-y-1/2 ${c}`}
           style={{ left: x(Math.min(0, value)), right: `calc(100% - ${x(Math.max(0, value))})` }} />
    </div>
  );
}

import type { ReactNode } from "react";

export function Panel({ title, aside, children, className = "" }:
  { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`border-t border-rule pt-4 ${className}`}>
      {(title || aside) && (
        <header className="mb-3 flex items-baseline justify-between gap-4">
          {title && <h2 className="text-[15px] font-semibold text-paper">{title}</h2>}
          {aside && <div className="text-xs text-mist">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return <p className="py-8 text-sm text-mist" role="status">Loading {what}…</p>;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="my-4 border-l-2 border-bear bg-deck px-4 py-3 text-sm" role="alert">
      <p>{message}</p>
      {onRetry && <button onClick={onRetry} className="mt-2 text-brass underline underline-offset-4">Try again</button>}
    </div>
  );
}

export function KV({ k, v, className = "" }: { k: ReactNode; v: ReactNode; className?: string }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1 text-sm ${className}`}>
      <span className="text-mist">{k}</span>
      <span className="num text-right">{v}</span>
    </div>
  );
}

export function Bias({ label }: { label: string }) {
  const c = label.includes("Bull") ? "text-bull" : label.includes("Bear") ? "text-bear" : "text-mist";
  return <span className={`font-medium ${c}`}>{label}</span>;
}

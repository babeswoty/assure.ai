import clsx from "clsx";
import type { SourceReference } from "@/types";

export function PhaseHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 pt-2 pb-1">
      <div className="w-1.5 h-5 bg-brand-500 rounded-sm" />
      <h2 className="text-base font-bold text-ink-800">{children}</h2>
    </div>
  );
}

export function SectionCard({
  number,
  title,
  children,
  disabled,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <section className={clsx("card", disabled && "opacity-50")}>
      <h2 className="text-sm font-bold uppercase tracking-wide text-ink-500 mb-3">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-500 text-white text-xs mr-2 align-middle">
          {number}
        </span>
        {title}
      </h2>
      <div className={disabled ? "pointer-events-none select-none" : undefined}>{children}</div>
    </section>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 text-red-800 px-4 py-3 text-sm">
      <strong className="font-semibold">Error: </strong>
      {message}
    </div>
  );
}

export function CategoryBadge({ category }: { category?: string | null }) {
  if (!category) return null;
  return <span className="badge bg-brand-100 text-brand-800 uppercase">{category.replace("_", " ")}</span>;
}

export function SourceRefDisclosure({ refs }: { refs: SourceReference[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <details className="mt-1 text-xs text-ink-500">
      <summary className="cursor-pointer select-none text-brand-700 hover:underline">
        View source ({refs.length})
      </summary>
      <ul className="mt-1 space-y-1 pl-3 border-l-2 border-brand-200">
        {refs.map((r, i) => (
          <li key={i}>
            <span className="font-mono">{r.source_id}</span>
            {r.locator ? <span className="font-mono"> [{r.locator}]</span> : null}
            {r.excerpt ? <span className="italic"> - "{r.excerpt}"</span> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function RacmField({
  label,
  value,
  wide,
}: {
  label: string;
  value?: string | null;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "sm:col-span-2" : undefined}>
      <dt className="font-semibold text-ink-700">{label}</dt>
      <dd className={clsx(!value && "italic text-ink-400")}>{value ?? "(not provided)"}</dd>
    </div>
  );
}

/** Splits prose into sentence-like chunks for display only - a pure
 * formatting aid (paragraphs are hard to scan), not a re-derivation of the
 * underlying value. Falls back to plain text when there's nothing
 * meaningful to split into steps. */
function splitIntoSteps(text: string): string[] {
  // Values that arrive already numbered ("1. ...\n2. ...") keep their own steps;
  // the list adds the numbers, so any existing ones are removed to avoid "1. 1.".
  const lines = text
    .split(/\n+/)
    .map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter(Boolean);
  if (lines.length > 1) return lines;
  return (lines[0] ?? "")
    .split(/(?<=[.!?])\s+(?=[A-Z0-9])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function StepText({ text }: { text: string }) {
  const steps = splitIntoSteps(text);
  if (steps.length < 2) {
    return <p>{steps[0] ?? text}</p>;
  }
  return (
    <ol className="list-decimal list-inside space-y-1">
      {steps.map((step, i) => (
        <li key={i}>{step}</li>
      ))}
    </ol>
  );
}

const RATING_STYLES: Record<string, string> = {
  Adequate: "bg-emerald-100 text-emerald-800",
  Inadequate: "bg-red-100 text-red-800",
  "Requires Human Review": "bg-amber-100 text-amber-800",
};

export function RatingBadge({ label }: { label: string }) {
  return (
    <span className={clsx("badge font-bold uppercase tracking-wide", RATING_STYLES[label] || "bg-ink-100 text-ink-600")}>
      {label}
    </span>
  );
}

export function DraftBadge() {
  return (
    <span className="badge bg-amber-100 text-amber-800 font-bold uppercase tracking-wide">
      Draft - requires human review
    </span>
  );
}

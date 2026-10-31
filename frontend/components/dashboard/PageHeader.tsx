import type { ReactNode } from "react";

/** The heading every dashboard view opens with, so they read as one product. */
export function PageHeader({
  title,
  lede,
  children,
}: {
  title: string;
  lede: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-6">
      <div className="min-w-0">
        <h1 className="font-head text-[22px] font-bold tracking-[-0.02em] text-white">{title}</h1>
        <p className="mt-1.5 max-w-2xl font-sans text-[13px] leading-relaxed text-white/50">
          {lede}
        </p>
      </div>
      {children && <div className="flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  );
}

/** A banner for views whose data has no endpoint behind it yet. */
export function PreviewNote({ children }: { children: ReactNode }) {
  return (
    <p className="mb-5 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 font-sans text-[11.5px] leading-relaxed text-white/45">
      {children}
    </p>
  );
}

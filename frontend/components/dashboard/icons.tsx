/**
 * Custom line-art icons for the dashboard shell.
 *
 * Hand-drawn rather than pulled from an icon set: the sidebar is the most
 * repeated surface in the product, and a lane-pair for the arena or a stacked
 * ledger reads as SYNAPSE's own vocabulary instead of a generic dashboard's.
 * All share one grid (24), one stroke weight, and inherit `currentColor`.
 */

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Glyph({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Two lanes racing — the arena. */
export const IconArena = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M3 8h11" />
    <path d="M3 16h7" />
    <circle cx="17.5" cy="8" r="2.5" />
    <circle cx="13.5" cy="16" r="2.5" />
    <path d="M21 4v16" strokeOpacity="0.45" />
  </Glyph>
);

/** Stacked rows against a time axis — the work ledger. */
export const IconLedger = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M4 4v16" strokeOpacity="0.45" />
    <path d="M8 7h12" />
    <path d="M8 12h8" />
    <path d="M8 17h10" />
    <circle cx="4" cy="7" r="1.3" fill="currentColor" stroke="none" />
    <circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none" />
  </Glyph>
);

/** A die with its pins — the model registry. */
export const IconModels = (props: IconProps) => (
  <Glyph {...props}>
    <rect x="7" y="7" width="10" height="10" rx="2" />
    <path d="M10 4v3M14 4v3M10 17v3M14 17v3M4 10h3M4 14h3M17 10h3M17 14h3" />
    <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
  </Glyph>
);

/** A key on its ring. */
export const IconKeys = (props: IconProps) => (
  <Glyph {...props}>
    <circle cx="8" cy="12" r="3.5" />
    <path d="M11.5 12H21" />
    <path d="M17.5 12v3.5" />
    <path d="M20.5 12v2.5" />
  </Glyph>
);

/** A meter dial — billing and usage. */
export const IconBilling = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M4 16a8 8 0 1 1 16 0" />
    <path d="M12 16l4.5-4.5" />
    <circle cx="12" cy="16" r="1.4" fill="currentColor" stroke="none" />
    <path d="M4 20h16" strokeOpacity="0.45" />
  </Glyph>
);

/** Two sliders — settings. */
export const IconSettings = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M4 8h16M4 16h16" strokeOpacity="0.45" />
    <circle cx="9" cy="8" r="2.5" />
    <circle cx="15" cy="16" r="2.5" />
  </Glyph>
);

export const IconSearch = (props: IconProps) => (
  <Glyph {...props}>
    <circle cx="11" cy="11" r="6" />
    <path d="M15.5 15.5L20 20" />
  </Glyph>
);

export const IconChevron = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M9 6l6 6-6 6" />
  </Glyph>
);

export const IconCollapse = (props: IconProps) => (
  <Glyph {...props}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" strokeOpacity="0.5" />
    <path d="M10 4v16" />
  </Glyph>
);

export const IconEye = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
    <circle cx="12" cy="12" r="2.5" />
  </Glyph>
);

export const IconEyeOff = (props: IconProps) => (
  <Glyph {...props}>
    <path d="M3 3l18 18" />
    <path d="M10.6 6.2A9.9 9.9 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-3 3.6" />
    <path d="M6.3 8.4A16 16 0 0 0 2.5 12S6 18 12 18c1.2 0 2.2-.2 3.2-.6" />
  </Glyph>
);

export const IconCopy = (props: IconProps) => (
  <Glyph {...props}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M15 5.5A1.5 1.5 0 0 0 13.5 4H5.5A1.5 1.5 0 0 0 4 5.5v8A1.5 1.5 0 0 0 5.5 15" />
  </Glyph>
);

import { useState } from "react";

/**
 * Resolves the nearest `.brand-manifest`-scoped ancestor in the DOM, for passing to
 * `DialogContent`'s `container` prop so dialogs portal inside the Manifest design system's
 * CSS scope (Archivo font, teal accent, 6px radius, muted tones) instead of escaping to
 * `document.body` and rendering stock/unthemed shadcn.
 *
 * Returns `undefined` (never `null`) when no `.brand-manifest` element is found — Base UI's
 * portal `container` prop falls through to its own default (`document.body`) on `undefined`,
 * whereas `null` can be interpreted as "don't portal at all".
 *
 * Resolved once via a lazy `useState` initializer (this app is client-rendered only, so reading
 * `document` during the initial render is safe — no SSR hydration mismatch to worry about). By
 * the time a user actually opens one of these dialogs, the surrounding `.brand-manifest`-scoped
 * page has already mounted, so the plain DOM query below reliably finds it.
 */
export function useBrandManifestContainer(): HTMLElement | undefined {
  const [container] = useState<HTMLElement | undefined>(
    () => document.querySelector<HTMLElement>(".brand-manifest") ?? undefined,
  );

  return container;
}

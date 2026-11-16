# Royal Scout visual system

Royal Scout uses an original, compact identity intended for a private, evidence-led cricket scouting workspace—not a public-facing score feed. The current mark combines an RS monogram, a precision ring, and a restrained seam accent. The selected emblem is optimized as `web/public/royal-scout-mark.webp` and used in the application. A small PNG favicon (`web/public/royal-scout-favicon.png`) provides broad browser compatibility, while the horizontal lockup is `web/public/royal-scout-logo.svg`. The React treatment lives in `web/src/components/brand-mark.tsx`.

## Tokens and components

- **Deep navy** (`navy-*`) is the structural color for navigation, primary actions, and analytical context.
- **Royal pink** (`royal-pink`) is the focused accent for active navigation, selection, and primary highlights; use sparingly.
- **Muted gold** (`royal-gold`) is reserved for secondary emphasis, never used to imply data confidence.
- **Surface and ink tokens** (`surface-*`, `ink-*`) are CSS-variable backed. They adapt to the selected light/dark theme without changing score meaning.
- Reuse `Card`, `CardHeader`, `CardBody`, `Stat`, `Badge`, and `PageHeader` rather than creating page-specific visual language.

## Interaction and accessibility

- Theme selection is a display preference only; it does not alter data, ranking, or methodology. It follows the system preference until the user selects a theme and tolerates unavailable browser storage.
- Navigation exposes the current page with `aria-current="page"`. Keyboard focus uses a visible pink ring.
- Motion is deliberately limited to a short page entrance, card hover, and loading sheen. All are disabled under `prefers-reduced-motion: reduce`.
- Keep textual labels and numbers legible in both themes. Status color supplements, and never replaces, a label or icon.
- Do not use the logo to imply a data source, official team affiliation, player endorsement, or verified status.

## Verification

Run from `web/`: `npm run typecheck`, `npm test`, and `npm run build`. The theme is client-applied after hydration; verify both theme states, keyboard focus, and reduced-motion behavior in an actual browser before release. The SVG assets are original project artwork and are not external player or team marks.

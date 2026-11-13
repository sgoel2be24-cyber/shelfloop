# Design

## Source of truth
Status: Active. Updated 2026-10-25. Covers the owner PWA, sign-in and operator workspace. Evidence: existing routes/components, API contract, seeded data, CSS, offline outbox and the approved ShelfLoop plan. Field interviews and microphone/device testing are not yet available.

## Brand
ShelfLoop is a practical neighbourhood trading assistant: composed, clear and approachable. Use forest green, pale mint and a small orange accent. Trust comes from visible provenance, owner approval and clear synthetic/sandbox labels. Avoid handwritten decoration, rotated badges, decorative emoji dashboards and unsupported savings claims.

## Product goals
Help owners capture stock, express needs and approve a costed action. Help operators understand the cluster, construct exchanges and recover from failures. Success is completion of real application flows, readable Hindi/English, no lost drafts and clear distinction between proposals and execution. Non-goals: banking, custody, production tax decisions and claims of field adoption.

## Personas and jobs
Owner: inexpensive phone, intermittent connectivity, short interactions and large touch targets. Operator: desktop/tablet, multiple shops and plans, needs dense but readable evidence and failure visibility.

## Information architecture
Owner: Today, Stock, Needs, Approvals. Operator: Overview, Planning, Exchange network, Failure rehearsal, Evidence. Sign-in makes the two roles explicit. A persistent workspace header contains language and mode status; technical detail stays in operator screens.

## Design principles
Show the next action before explanation. Use a small number of meaningful metrics. Separate real data from illustrations. Show monetary units and proposed/confirmed state. Empty and unavailable states must offer a useful next step. Reuse shared components and route navigation.

## Visual language
Tokens belong to frontend/tailwind.config.js and frontend/src/index.css. Forest #174C3C; ink #21352D; canvas #F5F7F3; orange #D86736; mint #DCEECD. Latin uses the system UI font; Hindi uses the existing locally bundled Baloo 2 subset. Cards have 16–22px radii, quiet borders and minimal elevation. Use an 8px spacing rhythm, restrained line icons and tabular numbers. No remote fonts or image dependencies. Motion is short and disabled for reduced-motion users.

## Components
Shared: buttons, fields, language toggle, logo, status badge, statistic, receipt, graph, loading skeleton and toast. Operator sidebar uses a dark forest surface with a mint active row. Owner navigation remains a four-item bottom bar. Buttons have visible disabled/loading states. Preserve backend-derived values rather than cosmetic sample charts.

## Accessibility
Target WCAG 2.2 AA: semantic regions, labelled controls, keyboard access, visible focus, minimum 44px primary targets and text alternatives. Charts include text labels. Error and connection states use text, not colour alone. Respect reduced motion. Avoid low-contrast primary body text.

## Responsive behavior
At 1024px+ use a 244px operator sidebar and a wider content canvas. At narrower widths use a compact header and horizontally scrollable navigation. Overview columns collapse at 1100px. At 390px forms and cards fit without page overflow; tables scroll inside their container. Owner reading width remains capped while desktop owner navigation can use the available canvas.

## Interaction states
Show explicit loading, retryable errors, no-data calls to action, disconnected status and queued-draft counts. Offline capture persists locally; approval requires the server. A stale approval never looks completed. Failed replay entries remain inspectable instead of being discarded. Sign-out preserves another owner's pending drafts but cannot replay them under a different account.

## Content voice
Plain, short language. Prefer 'Cash required', 'Needs covered', 'Stock on hold' and 'Practice transfer'. Money on a proposal is not measured savings. Label synthetic data and sandbox execution once in the workspace, with detailed assumptions in receipts and evidence. Keep core user actions bilingual.

## Implementation constraints
React/TypeScript/Vite with current dependencies; do not add a second design framework. Use same-origin /api so phone/tunnel use works. Production service worker caches the shell and assets; APIs remain network-only. Keep fonts local and import only needed weights/subsets. Verify build, lint, API regressions and desktop/mobile browser flows. Save screenshots of changed surfaces.

## Open questions
- [ ] Field validation: team to confirm terminology and reading burden with 3–5 owners; impact is copy and onboarding refinement.
- [ ] Local speech/OCR runtime availability: optional capability diagnostics must distinguish unavailable models from supported extraction.

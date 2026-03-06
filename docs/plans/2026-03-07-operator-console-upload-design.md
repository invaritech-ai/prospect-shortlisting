# Operator Console Upload Slice Design

## Scope
Build the first frontend vertical slice for operators to upload company files and inspect validation output.

## Visual Direction
Operator Console (light, dense, high signal):
- typography: Manrope + IBM Plex Mono
- colors driven by centralized design tokens
- compact cards + table layout for fast scanning

## Technical Decisions
1. Tailwind via Vite plugin (`@tailwindcss/vite`) for minimal config and fast setup.
2. Centralized design file at `src/design/tokens.css` with CSS variables for theme tokens.
3. Typed API client in `src/lib/api.ts` and data types in `src/lib/types.ts`.
4. First screen supports:
- upload CSV/TXT/XLS/XLSX
- fetch upload by ID
- display summary cards and validation errors table

## Success Criteria
- App builds and lints cleanly.
- Upload screen works against backend `/v1/uploads` and `/v1/uploads/{id}`.
- CORS allows local web dev origins.

## Next Step
Add scrape orchestration UI:
- create scrape job from domain
- enqueue run-all
- poll job status and render progress states

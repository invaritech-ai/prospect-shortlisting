# Vite 6 Stable Downgrade Design

## Goal
Move the frontend build off Vite 8 beta to a stable Vite 6 release while keeping React 19. Reduce build risk and avoid beta-only native bindings.

## Scope
- Update `apps/web/package.json` to use Vite 6 stable.
- Remove the Vite beta override.
- Keep React 19 and current UI behavior.
- Refresh `package-lock.json`.

## Non-Goals
- No UI/feature changes.
- No backend changes.
- No Docker/Coolify changes beyond ensuring a compatible Node version is used at build time.

## Proposed Changes
1. `apps/web/package.json`
   - `vite`: change from `^8.0.0-beta.13` to `^6.0.0` (stable).
   - Remove `overrides` for Vite.
   - Keep `@vitejs/plugin-react` and `@tailwindcss/vite` as-is (both support Vite 6).
2. Regenerate `package-lock.json` via `npm install` in `apps/web`.

## Compatibility Notes
- `@vitejs/plugin-react` 5.x requires Node `^20.19.0 || >=22.12.0`.
- Coolify must use Node 20.19+ or 22.12+ for the build.

## Test Plan
- Local: `npm install` then `npm run build` in `apps/web`.
- Deploy: ensure Coolify build passes and site serves.

## Rollback
- Revert commit(s) touching `package.json` and `package-lock.json`.

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

## Production deployment

Production is served by the multi-stage `apps/web/Dockerfile` (Node 22 build → nginx:alpine runtime). The matching nginx config (`apps/web/nginx.conf`) enforces the cache policy this app relies on:

- `/assets/*` — hashed by Vite, served with `Cache-Control: public, max-age=31536000, immutable`.
- `index.html`, root routes, SPA fallback, and 404s under `/assets/*` — served with `Cache-Control: no-store, must-revalidate` so a new deploy lands on the next request and stale HTML never pins missing asset hashes.

Coolify / any platform: set the build method to **Dockerfile** and point it at `apps/web/Dockerfile` (build context: `apps/web/`). The `apps/web/nixpacks.toml` is kept for reference only and is no longer the deployment entry point — the nixpacks staticfile provider doesn't let us control cache headers, which is what broke production on 2026-04-19.

Pass `VITE_API_BASE_URL` as a Docker build-arg if the SPA should call a non-same-origin API; defaults to same-origin (empty) so `fetch('/v1/...')` works behind the platform proxy.

Local smoke test:

```bash
docker build -t ps-web -f apps/web/Dockerfile apps/web
docker run --rm -p 8080:80 ps-web
# http://localhost:8080
```


Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

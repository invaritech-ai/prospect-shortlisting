# syntax=docker/dockerfile:1.7

# ─── Build stage ─────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS build

WORKDIR /app

# Install dependencies first to maximise layer caching across code changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the web source and build the production bundle.
COPY . .

# Build-time API base URL. Coolify should pass this via --build-arg when deploying.
# Falls back to same-origin (empty) so relative /v1/... calls work behind the proxy.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


# ─── Serve stage ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Replace the stock site config with our SPA + cache-control aware one.
# We drop both the default server block and the symlinked default vhost so
# our /etc/nginx/nginx.conf is the single source of truth.
RUN rm -f /etc/nginx/conf.d/default.conf \
 && rm -f /etc/nginx/nginx.conf

COPY nginx.conf /etc/nginx/nginx.conf

# Publish the built SPA to nginx's document root.
COPY --from=build /app/dist/ /usr/share/nginx/html/

EXPOSE 80

# Validate the config at build time so a bad edit fails the image build,
# not the first production request.
RUN nginx -t -c /etc/nginx/nginx.conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/_health >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]

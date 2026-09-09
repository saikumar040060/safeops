# Multi-stage: `dev` preserves the existing local docker-compose workflow
# (npm run dev) unchanged; `production` serves the Next.js standalone
# build with `node server.js` -- no dev server, no full node_modules.

FROM node:22-slim AS base

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web .

EXPOSE 3000


FROM base AS dev

CMD ["npm", "run", "dev"]


FROM base AS build

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build


FROM node:22-slim AS production

WORKDIR /app

# The node:* base images already ship a non-root `node` user (uid/gid
# 1000) for exactly this purpose -- no need to create another one.
# Standalone output already contains only the production dependencies it
# actually traced -- no `npm ci`/full node_modules needed in this stage.
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD node -e "require('http').get('http://localhost:3000/dashboard', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

# server.js is PID 1 (exec-form CMD) so it receives SIGTERM directly and
# shuts down gracefully.
CMD ["node", "server.js"]

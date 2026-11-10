# Dashboard image (standalone Next.js server).
# Build context is the repository root; the app lives in apps/dashboard.
FROM node:22-alpine AS build

WORKDIR /app
COPY apps/dashboard/package.json apps/dashboard/package-lock.json ./
RUN npm ci

COPY apps/dashboard ./
ARG WORKFORCE_API_BASE_URL=http://api:8000
ENV WORKFORCE_API_BASE_URL=$WORKFORCE_API_BASE_URL
# CI-time placeholder: the real key is injected at runtime, never baked in.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000
USER node
CMD ["node", "server.js"]

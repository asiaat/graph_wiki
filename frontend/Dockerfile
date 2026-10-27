FROM node:20-alpine AS builder

WORKDIR /app

# Copy the manifests first so the dependency layer is cached. A lockfile is
# optional: `npm ci` requires one to exist.
COPY frontend/package.json frontend/package-lock.json* ./

RUN if [ -f package-lock.json ]; then npm ci --prefer-offline; \
    else npm install --prefer-offline; fi

COPY frontend/ .

# Vite inlines these at build time, so they must be present in the build
# stage. Keeping them relative lets nginx proxy /api to the backend.
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_URL=/ws
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

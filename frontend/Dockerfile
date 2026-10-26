FROM node:20-alpine AS builder

WORKDIR /app

# Copy frontend
COPY frontend/package.json ./
COPY frontend/package-lock.json ./ 2>/dev/null || true

RUN npm ci --prefer-offline

COPY frontend/ .

# Build
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_WS_URL=ws://localhost:8000/ws
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
# syntax=docker/dockerfile:1
# Stage 1: Build stage
FROM node:20.19-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with BuildKit cache mount
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps

# Copy source code
COPY . .

# Build application (API_BASE will be replaced at runtime)
RUN npm run build

# Stage 2: Runtime with nginx
FROM nginx:1.25-alpine

# Install gettext for envsubst
RUN apk add --no-cache gettext

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy entrypoint script for environment variable substitution
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

# Use custom entrypoint for env var injection
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]

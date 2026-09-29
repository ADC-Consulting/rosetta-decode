# ---- Build stage: compile the static bundle ----
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Runtime stage: serve the static bundle + proxy the API ----
FROM nginx:1.27-alpine

# apache2-utils provides `htpasswd`, used by docker-entrypoint.sh to generate
# /etc/nginx/.htpasswd at container start when demo Basic Auth is configured
# (see DEMO_AUTH_USER/DEMO_AUTH_PASSWORD below). The auth-enabled directory is
# created here (not by the entrypoint) so nginx.conf's wildcard `include` of
# it always resolves to a real, if possibly empty, directory.
RUN apk add --no-cache apache2-utils \
    && mkdir -p /etc/nginx/conf.d/auth-enabled

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

# docker-entrypoint.sh conditionally enables HTTP Basic Auth (based on
# DEMO_AUTH_USER/DEMO_AUTH_PASSWORD) and then execs nginx itself.
ENTRYPOINT ["/docker-entrypoint.sh"]

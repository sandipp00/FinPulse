# ---- build the static site -------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_URL is deliberately unset: the browser calls the same origin and
# nginx forwards /api and /ws to the API container.
RUN npm run build


# ---- serve it (unprivileged nginx, listens on 8080) ---------------------------------
FROM nginxinc/nginx-unprivileged:1.31-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY proxy_params.inc /etc/nginx/proxy_params.inc
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1

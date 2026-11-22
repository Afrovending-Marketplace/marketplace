FROM node:20-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000
COPY frontend/ .
RUN rm -f .env
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL GENERATE_SOURCEMAP=false REACT_APP_SHOW_SAMPLE_CATALOG=false
RUN yarn build

FROM caddy:2-alpine
COPY --from=build /src/build /srv/www
COPY deploy/Caddyfile /etc/caddy/Caddyfile

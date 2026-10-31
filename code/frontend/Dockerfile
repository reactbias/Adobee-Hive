# Local/compose image: builds the static site and serves it with nginx,
# proxying /api and /mcp to the backend container. The hosted site is built by GitHub Pages instead.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

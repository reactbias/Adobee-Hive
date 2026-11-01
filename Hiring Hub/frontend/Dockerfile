# Stage 1: Build the React application
FROM node:18-alpine AS build

WORKDIR /app

ARG VITE_API_KEY
ARG VITE_ADMIN_TOKEN
ENV VITE_API_KEY=$VITE_API_KEY
ENV VITE_ADMIN_TOKEN=$VITE_ADMIN_TOKEN

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code and build
COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Remove default Nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy static assets from the builder stage
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
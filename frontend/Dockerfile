# Multi-stage: build the static bundle, then serve with nginx.
# (Used for the "pod behind the ALB" option; for S3+CloudFront, just upload
#  the `dist/` output from the build stage instead.)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# API URLs are baked at build time; override with --build-arg.
ARG VITE_INTAKE_URL
ARG VITE_RESULTS_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

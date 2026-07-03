# ── Stage 1: Build ────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_API_BASE_URL=http://localhost:8080
ARG VITE_AI_ENGINE_URL=http://localhost:8001
ARG VITE_WS_URL=ws://localhost:8001/ws/incidents
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AI_ENGINE_URL=$VITE_AI_ENGINE_URL
ENV VITE_WS_URL=$VITE_WS_URL

COPY package*.json .
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Serve (nginx) ────────────────────────────────────
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

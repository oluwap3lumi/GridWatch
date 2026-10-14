FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --include=optional --prefer-offline --fetch-retries=5 --fetch-retry-mintimeout=2000 --fetch-retry-maxtimeout=10000 --fetch-timeout=180000
COPY . .
RUN npm run build
EXPOSE 5173
CMD ["npm", "run", "dev"]

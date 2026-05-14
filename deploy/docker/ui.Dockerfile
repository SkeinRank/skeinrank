FROM node:22-alpine

WORKDIR /app/packages/skeinrank-ui

COPY packages/skeinrank-ui/package.json packages/skeinrank-ui/package-lock.json ./
RUN npm ci

COPY packages/skeinrank-ui ./

EXPOSE 5173

CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]

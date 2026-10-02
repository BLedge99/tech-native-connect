FROM node:20-slim

WORKDIR /app

# Copy manifests first so the install layer is cached when only source changes.
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
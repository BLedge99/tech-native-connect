FROM node:20-slim

WORKDIR /app

# Copy manifests first so the install layer is cached when only source changes.
# Both files: without the lock file `npm install` resolves @playwright/test to
# whatever is newest, and the browser revision the test asks for stops matching
# the one baked into the image.
COPY package.json package-lock.json ./
RUN npm ci

# Chromium itself. Without this every Playwright test fails with "Executable
# doesn't exist" — which reads like a broken app rather than a missing browser,
# and the cache lives outside /app so it does not survive a container recreate.
RUN npx playwright install chromium

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
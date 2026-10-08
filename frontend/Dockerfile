FROM node:20-slim

WORKDIR /app

# System libraries for Playwright's bundled Chromium. Without these the browser
# fails to launch with "libglib-2.0.so.0: cannot open shared object file", which
# is what made the dev-tooling suite report 6 failures that had nothing to do
# with the tooling. `npx playwright install-deps` would do this too, but doing
# it here keeps it in the image layer rather than needing a manual step.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libx11-6 libxcb1 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests first so the install layer is cached when only source changes.
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
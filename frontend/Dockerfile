FROM node:20-slim

WORKDIR /app

# Copy manifests first so the install layer is cached when only source changes.
# Both files: without the lock file `npm install` resolves @playwright/test to
# whatever is newest, and the browser revision the test asks for stops matching
# the one baked into the image.
COPY package.json package-lock.json ./
RUN npm ci

# Chromium itself, plus the shared libraries it links against. `--with-deps`
# runs apt-get for them; without it every Playwright test fails to launch with
# "libglib-2.0.so.0: cannot open shared object file" — which reads like a
# broken app rather than a missing system library. The browser cache lives
# outside /app so it does not survive a container recreate.
RUN npx playwright install --with-deps chromium

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
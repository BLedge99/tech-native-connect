FROM node:20-slim

WORKDIR /app

# System libraries for Playwright's bundled Chromium. `playwright install`
# below downloads the browser but not these, and node:20-slim does not ship
# them, so without this block every Playwright test fails with
# "libglib-2.0.so.0: cannot open shared object file". Same block as on main.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libx11-6 libxcb1 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests first so the install layer is cached when only source changes.
# Both files: without the lock file `npm install` resolves @playwright/test to
# whatever is newest, and the browser revision the test asks for stops matching
# the one baked into the image.
COPY package.json package-lock.json ./
RUN npm ci

# Chromium itself. Without this every Playwright test fails with "Executable
# doesn't exist" — which reads like a broken app rather than a missing browser,
# and the cache lives outside /app so it does not survive a container recreate.
#
# Optional: it is the largest layer in the image, and on some Windows/WSL
# machines Docker crashes saving it ("failed to receive status: rpc error ...
# EOF"). The app itself never needs it. `run.bat tunnel` builds with
# INSTALL_TEST_BROWSER=0; everything else keeps the default, so the E2E
# suite works unchanged. After a tunnel build, run `.\run.bat build` before
# Playwright tests (or `run.bat devcheck`, which installs it on demand).
ARG INSTALL_TEST_BROWSER=1
RUN if [ "$INSTALL_TEST_BROWSER" = "1" ]; then npx playwright install chromium; fi

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
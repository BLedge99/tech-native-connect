# Exposing Bootcamp Connect via Cloudflare Tunnel

This guide explains how to run Bootcamp Connect on your local machine and expose
it to the public internet using Cloudflare Tunnel.

---

## 1. How it works

- The full application (`db`, `backend`, `frontend`, `mailpit`) runs locally in Docker.
- A lightweight `tunnel` container runs `cloudflare/cloudflared:latest`.
- Cloudflare creates an encrypted outbound tunnel from your local machine to Cloudflare's global edge network.
- **No router configuration, port forwarding, or firewall opening is required.**
- By default, it runs as a **Cloudflare Quick Tunnel** (`https://<random-name>.trycloudflare.com`):
  - 100% free
  - No Cloudflare account required
  - Free automatic SSL/TLS certificate
  - Full WebSocket and HTTP proxying

---

## 2. Quickstart (One command)

From PowerShell or CMD in the project root:

```powershell
.\run.bat tunnel
```

`run.bat tunnel` will:
1. Start the Docker containers (`db`, `backend`, `frontend`, `mailpit`, and `tunnel`).
2. Wait for Cloudflare to establish the tunnel.
3. Print your live public URL on the screen in cyan:

```
===================================================
  Cloudflare Tunnel is LIVE! Open to web traffic:  
  https://random-words-1234.trycloudflare.com
===================================================
```

Any web browser, phone, or colleague can open that URL and use the live application immediately.

---

## 3. Useful commands

| Command | Purpose |
|---|---|
| `.\run.bat tunnel` | Build and start all services in the background and display the live URL |
| `.\run.bat url` | Show the active Cloudflare Tunnel URL |
| `.\run.bat logs` | Follow all container logs (including tunnel output) |
| `.\run.bat down` | Stop the services |
| `.\run.bat clean` | Stop the services and reset database volume |

You can also view the tunnel logs directly at any time:

```powershell
docker compose logs -f tunnel
```

---

## 4. Features enabled for web visitors

1. **Native WebSockets over WSS:**
   The backend allows `.trycloudflare.com` origins and wildcards, so real-time 1:1 chat and live notification toasts work seamlessly across the tunnel.

2. **Inline Magic Links (`DEMO_EXPOSE_MAGIC_LINKS=true`):**
   External visitors cannot access the local Mailpit inbox on `localhost:8025`. With `DEMO_EXPOSE_MAGIC_LINKS=true`, requesting a sign-in link displays the single-use magic link directly in the browser so any visitor can sign in without needing access to your local machine.
   The link is built from the browser's own `Origin` (the tunnel URL) when that origin is trusted, so it works on the visitor's device; an untrusted or missing `Origin` falls back to `APP_URL`.

3. **Seeded Test Accounts:**
   - **Business Developer:** `priya@example.com` / `demo-password-123`
   - **Admin:** `ben@bootcamp.example.com` / `bootcamp-dev-admin`

---

## 5. Optional: Using a custom domain / Named Tunnel

If you have your own Cloudflare account and a registered domain:

1. Create a tunnel in the [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) (Networks → Tunnels).
2. Set the public hostname to point to `http://frontend:5173`.
3. Copy the tunnel token.
4. Set it in `.env`:
   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=eyJh...
   ```
5. In `docker-compose.yml`, change the tunnel service command to:
   ```yaml
   command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
   ```
6. Run `.\run.bat tunnel`.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| URL shows "502 Bad Gateway" | Frontend still starting. Wait ~30 s; check `docker compose logs frontend`. |
| First page load is slow | Vite dev server sends many small modules; the first load over the tunnel can take 10–20 s. Later loads are cached. |
| Old URL stopped working | Quick Tunnel URLs change every time the `tunnel` container restarts. Run `.\run.bat url` for the current one. |
| "No tunnel URL yet" | `docker compose logs tunnel`. Corporate/school networks sometimes block outbound port 7844; cloudflared then falls back to HTTP/2 over 443 on its own. |
| Build dies with `failed to receive status: rpc error ... EOF` | Docker ran out of memory saving the frontend image. `run.bat tunnel` now builds without the Playwright browser and one image at a time; if it still happens, restart Docker Desktop and run `docker builder prune -f`. |
| Playwright tests say "Executable doesn't exist" after a tunnel run | The tunnel build skips the test browser. `.\run.bat build` puts it back. |
| The PC sleeps | The tunnel lives on your machine: keep it awake and Docker running for the whole demo. |

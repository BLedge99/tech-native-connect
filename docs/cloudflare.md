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

`run.bat tunnel` does not print the URL until `GET <url>/api/v1/health` actually
answers `200`. A Quick Tunnel hostname is not serving traffic the moment the log
line appears — it still has to register on Cloudflare's edge — so a banner
printed on the log line alone was a coin flip.

---

## 2a. If you see Cloudflare error 1033

> **1033 Cloudflare Tunnel — "the edge knows this hostname, but no cloudflared
> instance is registered for it."** The URL resolved. Nothing is behind it.

| Symptom | Cause | Fix |
|---|---|---|
| 1033 for other people, works for you | You are looking at a **dead hostname** from an earlier run. `docker compose logs tunnel` prints the container's **entire history**, and a restarted cloudflared gets a **new** random hostname while the old one stays in the log | `.\run.bat url` now prints the **last** hostname, the live one. Re-run `.\run.bat tunnel` |
| 1033 for everyone, including you | The tunnel container died | `.\run.bat tunnel`. There is deliberately no `restart:` policy — see below |
| The banner says **"NOT serving traffic yet"** | The URL did not answer within 60 s | Wait and re-run `.\run.bat url`, or read `docker compose logs tunnel` |

**The hostname changes.** That is not a bug in the app — a Quick Tunnel
hostname is random and lives only as long as the cloudflared process. If the
container is recreated for any reason, the previous URL is dead and you must
re-share the new one. **The `tunnel` service deliberately has no
`restart: unless-stopped` policy**, because a silent restart would come back on
a different hostname and orphan every URL you had already handed out without
telling you. It is better to notice. Use a named tunnel (§5) if you need a URL
that survives a restart.

---

## 2b. Verifying the tunnel from outside

`frontend/tests/tunnel.spec.ts` drives the public URL from inside the Playwright
container — a **different network namespace** from the host, so it exercises the
real off-machine path rather than the host's loopback:

```powershell
.\run.bat tunnel
docker compose exec -T -e TUNNEL_URL=https://<the-printed-url> frontend npx playwright test tunnel.spec.ts
```

It checks the health endpoint, that the landing page and its assets load, that
sign-in sets a cookie for the tunnel host, and that the WebSocket handshake is
accepted from a `trycloudflare.com` origin. Without `TUNNEL_URL` it skips, so
the default suite is unaffected.

---

## 3. Useful commands

| Command | Purpose |
|---|---|
| `.\run.bat tunnel` | Build and start all services in the background and display the live URL |
| `.\run.bat url` | Print the current tunnel URL (the live one, verified) |
| `.\run.bat logs` | Follow all container logs (including tunnel output) |
| `.\run.bat down` | Stop the services |
| `.\run.bat clean` | Stop the services and reset database volume |

`run.bat url` and `run.bat tunnel` both delegate to
[`scripts/tunnel-status.ps1`](../scripts/tunnel-status.ps1), which holds the URL
extraction and the health check.

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

A named tunnel's hostname is fixed, so it survives restarts and never produces
a 1033. Keep the `restart:` policy **off** the service either way — it is not
what stops a named tunnel from dying, and a silent restart is still a silent
restart.

> **Note.** `CORS_ORIGINS` and the `is_allowed_origin` check in
> `routers/messaging.py` already accept `*.trycloudflare.com`, but a **custom
> domain** is not in either allowlist. Set `CORS_ORIGINS` to your own origin
> before using one, or the WebSocket handshake will be refused with close
> `1008` and live messaging will be dead for visitors.

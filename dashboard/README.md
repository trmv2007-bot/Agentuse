# Self-hosted Minecraft dashboard

A full administration panel for Minecraft running on your own Linux PC or VPS. It is separate from the temporary GitHub Actions workflow, because GitHub runners cannot provide durable server storage or a reliable control panel.

## What it manages

- Paper **or** official Vanilla server selection on each start
- Start, safe stop, and restart controls
- Console log, command input, and online-player refresh
- Make a player an operator and add/remove a whitelist entry
- Edit `server.properties` while the server is stopped
- World backup creation and direct backup downloads
- Java and system memory display

Paper supports plugins in `plugins/`; Vanilla intentionally ignores that directory.

## Local use — no password

Install Node.js 20+, Java 21, Python 3, `curl`, and `tar`, then clone this repository and run:

```bash
export MAX_RAM=4G       # optional
npm start
```

The panel is local-only by default at [http://127.0.0.1:3000](http://127.0.0.1:3000), with no username or password. Minecraft listens on TCP port `25565`.

## Internet / VPS use — HTTPS and password required

Do not expose the dashboard directly. Keep it bound to loopback and put Nginx plus HTTPS in front of it:

```bash
export MC_DASHBOARD_USERNAME=admin
export MC_DASHBOARD_PASSWORD='long-unique-random-password'
export DASHBOARD_HOST=127.0.0.1
npm start
```

1. Point a domain such as `dashboard.example.com` to your VPS.
2. Copy [`nginx.conf.example`](nginx.conf.example) to `/etc/nginx/sites-available/minecraft-dashboard`, replace the domain, and enable it.
3. Run `sudo certbot --nginx -d dashboard.example.com` to enable HTTPS.
4. Allow HTTPS (TCP 443) in the firewall. **Do not open port 3000.**

Nginx proxies to localhost, while the dashboard’s required Basic Auth password protects the administrative controls. Use a VPN such as Tailscale instead if you do not want a public web endpoint.

For public player access, set up a Minecraft tunnel such as Playit on the same machine or forward **only** TCP `25565`. Never share dashboard credentials with players.

## Backups and data

Backups are `.tar.gz` files in `backups/`. They persist as long as the repository folder/disk does. Download them from the panel; restoring a backup means stopping the server and extracting it into `server/`.

For the most consistent backup, stop the server first. The dashboard can create one while online, but Minecraft may be writing world files at the same time.

## systemd service

Create `/etc/systemd/system/minecraft-dashboard.service`, replacing the repo path and password:

```ini
[Unit]
Description=Minecraft dashboard
After=network.target

[Service]
Type=simple
User=minecraft
WorkingDirectory=/home/minecraft/MCserver
Environment=MC_DASHBOARD_USERNAME=admin
Environment=MC_DASHBOARD_PASSWORD=replace-this-with-a-long-random-password
Environment=MAX_RAM=4G
Environment=DASHBOARD_HOST=127.0.0.1
ExecStart=/usr/bin/node dashboard/server.js
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Protect and enable the unit:

```bash
sudo chmod 600 /etc/systemd/system/minecraft-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now minecraft-dashboard
```

Inspect it with `sudo journalctl -u minecraft-dashboard -f`.

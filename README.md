# Temporary Minecraft server via GitHub Actions

This repository can start a **temporary Java Edition Minecraft server** from a manually triggered GitHub Actions run. It is useful for a short play session or testing; GitHub Actions is **not** a 24/7 game host. A job is stopped after the selected duration (and GitHub applies its own runner limits), all world changes disappear when it stops, and availability depends on your Actions quota.

For a permanent public server, use a Minecraft host, a VPS, or a self-hosted GitHub Actions runner instead.

## Before starting

1. Open this repository on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
2. Add a secret called `PLAYIT_SECRET`. Create it by signing in to [playit.gg](https://playit.gg), creating a Minecraft Java tunnel, and copying that tunnel's secret key. Do not put this value in the workflow file.
3. Commit/push these files to GitHub.

The workflow only starts when you explicitly run it, so it does not consume Actions minutes on pushes.

## Self-hosted quick start

For starting the dashboard, launching Minecraft, and sharing a LAN/public join address, see the step-by-step [Start and join guide](docs/STARTING_AND_JOINING.md).

## Start a server with GitHub Actions

1. Open the repository’s **Actions** tab.
2. Select **Run Minecraft server**, then choose **Run workflow**.
3. Pick a Minecraft version (for example `1.21.4`), RAM, and session duration.
4. Open the running workflow and expand **Run Minecraft server**. The log prints a `playit.gg` address. Share that exact address with Java Edition players.

The default is Paper, a high-performance server compatible with vanilla Java clients. It downloads the newest Paper build for the selected Minecraft version when the job starts.

## Server configuration

Edit [`server.properties`](server.properties) to change game mode, difficulty, whitelist, view distance, and other standard Minecraft settings. The startup script copies it into the temporary server directory.

To install plugins, create a `plugins/` directory in the repository and add plugin JARs there; the workflow copies them before startup. Only use plugins you trust and that match the chosen Paper/Minecraft version.

## Important limitations

- **Not persistent:** worlds, player data, and server changes are deleted when the workflow ends. Download a backup from the workflow’s **Artifacts** section before it expires.
- **Temporary:** stop time is limited by the workflow input and GitHub’s runner limits.
- **Private tunnel key:** `PLAYIT_SECRET` must stay a GitHub Actions secret. If it is ever exposed, rotate it in Playit.
- **EULA:** triggering the workflow confirms that you accept the [Minecraft EULA](https://www.minecraft.net/eula).

## Self-hosted web dashboard

A self-hosted dashboard with Paper/Vanilla selection, start/stop/restart, logs, console commands, player/whitelist controls, backups, memory monitoring, and server-settings editing is included in [`dashboard/`](dashboard/README.md). It runs beside Minecraft on **your own Linux machine or VPS**, not on GitHub Actions. It stays password-free when local-only and is designed to sit behind HTTPS plus password protection for Internet/VPS access. Follow the [dashboard setup guide](dashboard/README.md).

## Local or self-hosted use

On a Linux machine with Java 21 installed:

```bash
export MC_VERSION=1.21.4
export MAX_RAM=2G
./scripts/start-server.sh
```

The local script starts only Minecraft; connect locally on port `25565`, or run a tunnel service such as Playit separately. The GitHub Actions workflow starts the Playit tunnel for you.

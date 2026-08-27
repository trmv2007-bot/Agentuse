# Start and join the Minecraft server

This guide is for the **self-hosted dashboard** setup: Minecraft runs on your own Linux computer or VPS.

## 1. Install the requirements

Install Java 21 or newer, Node.js 20 or newer, Python 3, `curl`, and `tar` on the machine that will run the server.

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y openjdk-21-jre-headless nodejs npm python3 curl tar
java -version
node --version
```

## 2. Start the dashboard

From the repository folder:

```bash
export MAX_RAM=4G       # choose RAM appropriate for the host; 2G is also fine for a few players
npm start
```

Open this **on the server machine**:

```text
http://127.0.0.1:3000
```

The dashboard is local-only and needs no password in this mode.

## 3. Start Minecraft

1. At the top of the dashboard, select **Paper** (recommended, supports plugins) or **Vanilla**.
2. Click **Start server**.
3. Wait for the console to show that the server is ready. The first start downloads the server software, so it can take a few minutes.
4. Do not close the terminal that is running `npm start`.

The dashboard buttons safely stop/restart the server and save its world.

## 4. Let people join

The default configuration has `white-list=false`, so anyone with the server address can join. It also currently has `online-mode=false`, meaning Minecraft accounts are not verified; only share the address with people you trust.

### Players on the same Wi-Fi / LAN

On the server machine, find its LAN address:

```bash
hostname -I
```

Share the first address, followed by `:25565`, for example:

```text
192.168.1.50:25565
```

A player opens **Minecraft Java Edition → Multiplayer → Add Server**, enters any name, pastes that address, and selects **Join Server**.

### Players outside your network

Choose one approach:

- **Playit.gg tunnel (recommended):** create a Minecraft Java tunnel in Playit, run its agent on the server machine, then share the address Playit gives you.
- **Router port forwarding:** forward **TCP port 25565** from your router to the server machine's LAN IP. Allow it through the host firewall, then share `YOUR-PUBLIC-IP:25565` (or a domain name). Do not forward dashboard port `3000`.
- **VPS:** allow TCP `25565` in the VPS/cloud firewall and share the VPS public IP.

For Ubuntu's UFW firewall, allowing Minecraft is:

```bash
sudo ufw allow 25565/tcp
```

## 5. Optional: restrict access

To admit only friends, stop the server, change this dashboard setting, save it, then start the server again:

```properties
white-list=true
```

Use the dashboard's **Whitelist** button to add each exact Minecraft username. You can make trusted users administrators through **Make OP**.

## Keep the dashboard private

Players only need the Minecraft address and port `25565`; never give them the dashboard URL. If you need dashboard access over the internet, follow [`dashboard/README.md`](../dashboard/README.md) to put it behind HTTPS with a password.

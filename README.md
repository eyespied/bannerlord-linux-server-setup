# Bannerlord Linux Server Setup

Reusable setup and SSH operations for one or several Bannerlord dedicated servers on **Ubuntu 24.04 x86_64**. Installs SteamCMD, downloads the official dedicated server, builds the compatible runtime and prepares isolated Docker instances. No community mods, custom maps, production addresses, database services or credentials are included.

Each instance gets its own game files, module folders, configuration, token and port. Copies use filesystem reflinks where available to save space. Changes to one instance do not silently change another.

## New machine: quick start

Buy an Ubuntu 24.04 **x86_64** VPS with a public IP. Set up your provider SSH access first. Disk/RAM needs depend on the number of instances, mods and players; each instance can require a full game copy when reflinks are unavailable. Keep backups off the VPS.

```bash
sudo apt-get update && sudo apt-get install -y git python3
sudo git clone https://github.com/eyespied/bannerlord-linux-server-setup /opt/bannerlord-linux-server-setup
cd /opt/bannerlord-linux-server-setup
sudo cp settings.example.json settings.json
sudo nano settings.json
bash bootstrap.sh --plan
sudo bash bootstrap.sh
sudo python3 bl.py token server1
sudo cp config.example.txt /tmp/my-server.txt
sudo nano /tmp/my-server.txt
sudo python3 bl.py config server1 /tmp/my-server.txt
sudo python3 bl.py start server1
sudo python3 bl.py status
sudo python3 bl.py logs server1
```

Set the administrator password and a valid Native map/game mode before starting. Check Steam's supplied `Modules/Native/ds_config_*.txt` examples for the installed version. Generate a private TaleWorlds token in the game's multiplayer lobby using `customserver.gettoken`; paste it at the hidden `token` prompt. Steam's anonymous *download* is separate from authenticated *hosting*. Tokens expire and must be replaced when required. [Official hosting guide](https://moddocs.bannerlord.com/multiplayer/hosting_server/).

Open the configured **UDP** game ports and **TCP** map-download/admin-panel ports in the provider firewall and host firewall. Preserve SSH access when changing firewall rules. This installer deliberately does not replace firewall rules. The example uses 7210 and 7220. A strong `AdminPassword` is required by this tool before starting the built-in web panel.

The installer does not start games automatically. It refuses an existing unmanaged installation directory. Repeat provisioning preserves existing instance folders, configs and tokens. A partially installed managed root can be retried. Docker is installed only if missing; an existing Docker installation must already support Compose v2.

## Settings

Copy `settings.example.json` to ignored `settings.json`.

| Field | Meaning |
|---|---|
| `root` | New dedicated directory directly under `/srv`, default `/srv/bannerlord`. |
| `instances[].name` | Unique instance/service name. |
| `port` | Unique TCP/UDP port, 1024–65535. |
| `tickrate` | Server tickrate, 10–120. |
| `modules` | Ordered module IDs, starting with `Native`, `Multiplayer`. Custom folders must match their manifest IDs. |
| `restart` | `unless-stopped`, `on-failure` or `no`. |

Add another instance entry and rerun provisioning to prepare its isolated folder. Set its token and config separately. Editing settings does not mutate a running container; `render` regenerates Compose and `restart NAME` applies its settings. Avoid renaming existing instances or roots without an explicit data migration. Remove retired instances with `stop` before removing their settings entry.

## SSH from your PC

Install Python 3 and OpenSSH. Use an SSH config alias (keys recommended), such as `my-server`. The host repository location defaults to `/opt/bannerlord-linux-server-setup`; override with `--repo`. Your SSH user needs sudo to operate Docker and protected data; this is an administrator tool, not a restricted operator account.

```powershell
python remote.py --host my-server menu
python remote.py --host my-server status
python remote.py --host my-server stop server1
python remote.py --host my-server config server1 .\my-config.txt
python remote.py --host my-server upload-mods server1 .\MyModule.zip
python remote.py --host my-server render
python remote.py --host my-server start server1
```

`server.bat` is a Windows convenience wrapper around `remote.py`; it accepts the same arguments and pauses on failure. The SSH menu provides status, start/stop/restart, logs and backup. The game's built-in password-protected web administration panel is available on the instance's TCP port after startup; this repo does not expose a second public web dashboard.

`remote.py` uploads to a unique temporary host path with SCP and removes that upload afterward. Secrets are never passed as command-line arguments by this helper. Config and mod upload require the selected instance to be stopped and take a private backup first. Upload does not automatically restart the game.

## Mods and maps

Create a ZIP containing `MyModule/SubModule.xml` and its server files, then upload it with `upload-mods NAME FILE.zip`. Multiple module folders are supported. Native/Multiplayer replacements, links, traversal, duplicate/case-colliding paths and archives over 20 GiB unpacked are rejected. Add IDs to the ordered `modules` setting and run `render` before starting. A manifest alone does not prove Linux compatibility: mods may require Linux libraries, path/case fixes or their own runtime dependencies.

Custom scenes can be copied privately to `instances/NAME/game/Modules/Multiplayer/SceneObj/SceneName` while stopped, using SCP/rsync over SSH. Register the scene in server configuration. The native map downloader serves SceneObj contents, not a full modpack; clients still need matching custom assets/modules. [Official map-download requirements](https://moddocs.bannerlord.com/multiplayer/hosting_server/).

## Updating and recovering

```bash
sudo python3 bl.py update                 # update Steam base only; games keep running
sudo python3 bl.py stop server1
sudo python3 bl.py apply-update server1   # backup, new base, preserve custom modules/config/scenes
sudo python3 bl.py start server1
sudo python3 bl.py logs server1
sudo python3 bl.py backup server2         # stop server2 first
```

`apply-update` keeps the previous game folder for rollback. It preserves the main server config, token, custom module folders and custom Multiplayer scenes absent from the new base. Other ad-hoc edits to Native/base files are not carried forward; they remain in the previous folder and backup. Test updated mod compatibility before updating other instances.

Backups in `ROOT/backups` contain game files and the private token, mode 600. Copy these plus `settings.json` off-host using encrypted storage. They are intentionally ignored by Git. To recover an instance, stop it, rename its current game folder, and extract the trusted backup into that instance directory (it contains `game/` and `token`); set token mode 600, regenerate Compose, then start and inspect logs. Only restore archives you created and trust. A new VPS can run the quick start and then restore these private files. The GitHub repo alone cannot restore your maps/mods/passwords.

## Runtime and validation

The compatibility container uses .NET/ASP.NET 6.0.36 and Bullseye libraries, matching two inspected existing Ubuntu deployments. The game requires that older stack; the container uses signed [Debian archived packages](https://www.debian.org/distrib/archive) rather than broken old live package URLs. .NET 6 is an older runtime; a future game version may require revisiting the image and assembly overlay. It is not replaced with a newer major runtime without testing.

`python3 -m unittest -v test_setup.py` checks config validation, archive safety and isolated Compose generation. See [VALIDATION.md](VALIDATION.md) for actual test evidence and remaining startup/gameplay limits. The installer targets a fresh machine; running a plan or unit tests does not prove full provisioning or player connectivity.

## Files and secrets

| File | Purpose |
|---|---|
| `bootstrap.sh` | Installs host dependencies and calls provisioning; `--plan` changes nothing. |
| `bl.py` | Validates, provisions, manages instances, tokens/configs, uploads, updates and backups. |
| `remote.py` / `server.bat` | SSH/SCP control from another computer. |
| `runtime/Dockerfile` / `entrypoint.sh` | Compatible runtime and game launch arguments. |
| `settings.example.json` / `config.example.txt` | Generic editable templates; no real secrets. |

There are no required environment variables. Private tokens are read from per-instance files; settings and game configs remain local. The token reaches the game process via its required launch argument; trusted host administrators can inspect it. Do not publish Docker inspection output, backups or private configs. No Steam/game binaries are redistributed here.

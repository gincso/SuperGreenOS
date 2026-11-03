# SuperGreenOS GUI Compiler

A small web page to change SuperGreenOS settings and recompile, without
using the terminal. Stdlib-only Python, no pip packages.

## Run it

```bash
cd gui-compiler
# SGL_REPO defaults to the repo root (the parent of gui-compiler/).
# Override it if the repo lives elsewhere:
#   SGL_REPO=/root/SuperGreenOS-build python3 server.py 8002
python3 server.py 8002
```

Open http://<your-server>:8002 in a browser.

On first start it generates a token in `token.txt` (600 permissions).
Get it on the server with:

```bash
cat gui-compiler/token.txt
```

Paste it into the page once; your browser remembers it.

## What it does

- Profiles: driver, controller, pickle, solo, screen, tips
- Settings editor for `modules.<module>.fields.<field>.default` and each
  module's `enabled` flag, with search. Saving makes a `.bak` backup.
- Compile button: runs the ESP-IDF v3.3.6 Docker build for the chosen
  profile, shows the live log, and lists downloadable firmware files
  (firmware.bin, bootloader.bin, partitions.bin, ota_data_initial.bin)
  under `builds/<profile>-<timestamp>/`.

## Notes

- CUE regeneration is skipped on purpose: the old `config_gen/*.cue`
  files fail on modern CUE, and the committed `config.*.json` files are
  the source of truth. Edit the JSON through this page.
- `sdkconfig.defaults` sets `CONFIG_PYTHON="python"` because the
  IDF 3.3.6 image is Python 3 only.
- This page is token-protected but plain HTTP. Put it behind HTTPS
  (or a VPN / firewall allow-list) before exposing it publicly.

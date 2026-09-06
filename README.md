# xsh-lib/hellocore

xsh utilities for the **HelloCore PTZ20X2** USB camera — an EOL AI-tracking
healthcare PTZ (20x optical zoom, ~360°/180° gimbal, single USB-C, no
buttons/remote and no vendor software available). Fully host-controllable over
its VISCA serial channel once you know which command families it implements.

The one USB-C cable enumerates **two** independent interfaces:

| Interface | macOS device | Purpose |
|---|---|---|
| UVC video | `hello PTZ20X2` camera | the image (OBS, etc.) |
| USB-serial | `/dev/cu.usbserial-*` | **VISCA control** (9600 8N1, addr 1) |

OBS only reads the video interface, which is why it cannot move the camera —
pan/tilt/zoom live entirely on the serial control channel.

## VISCA control map (reverse-engineered on this unit)

| Function | Command | Works? |
|---|---|---|
| Zoom (absolute) | `81 01 04 47 0p0q0r0s FF` | ✅ |
| Pan/Tilt **absolute** | `81 01 06 02 ps ts <pan4> <tilt4> FF` | ✅ |
| Pan/Tilt **relative** | `81 01 06 03 ...` | ✅ |
| **Pan-Tilt Reset / calibrate** | `81 01 06 05` | ✅ full grind-free recenter → (0,0), ~20s |
| Zoom / PT / power inquiries | `81 09 04 47` / `81 09 06 12` / `81 09 04 00` | ✅ |
| Pan/Tilt **jog/drive** | `81 01 06 01 ...` | ❌ silently ignored |
| **HOME** | `81 01 06 04` | ❌ `ERR41` not-executable |
| Pelco-D / Pelco-P | — | ❌ not spoken |

**Gotcha:** the jog/drive (`06 01`) and HOME (`06 04`) families are NOT
implemented — jog returns nothing, HOME errors `ERR41` — which makes the camera
look uncontrollable at first. Absolute/relative positioning is the way in, and
**Pan-Tilt Reset (`06 05`)** runs the unit's own absolute-referencing calibration
(same as power-on) to recenter cleanly.

### Measured envelope (VISCA units)

Important: the **command window** is much smaller than the **physical** travel,
and firmware clamps **both** absolute (`06 02`) **and** relative (`06 03`) targets
to that one window — there is **no command path past it** (jog `06 01` is
unimplemented; Pan-Tilt Limit Set/Clear `06 07` is accepted but has no effect on
the cap; large open-loop targets don't move the mechanism any further — verified
by eye). The extra physical travel is only touched by the internal
reset/calibration sweep or by hand. The window also sits **high** in the tilt
travel: tilt-up `+1200` is ~2 clicks from the physical top (near-maxed), while
tilt-down `-576` stops well above the physical bottom.

- **Zoom:** `0x0118` (1x/wide) … `0x3FE6` (20x/tele) — pure optical, no digital.
  Min focus distance ≈ 80 cm at 20x (not short at 1x either).
- **Pan:** command window `-2018` … `+2147`; **less than** the ~360° physical range.
- **Tilt:** command window `-576` … `+1200`, only **~60°** of the physical ~180°+
  travel (asymmetric).

`±100%` maps to these window edges — the maximum a command can reach. The edges
sit well inside the physical stops, so commanding an edge parks the servo there
cleanly (no stop contact, no grind), and within the window positioning is **exact
and clean** (round-trips return to the same value, no backlash).

### Active position-hold & fail-safes

The gimbal holds its commanded position under motor torque, so a position inquiry
reports the *commanded* target, not where you push it by hand — and hand-moving is
fought back (grind), which also blocks the control MCU from answering inquiries.
`move()` / `set_pt` / `set_zoom` therefore:

- **skip** a move already within tolerance of the target (no needless re-grind);
- **detect a stall early** — if pan/tilt stops progressing toward target (a stop,
  e.g. after a hand-move pushed it past the window), re-command a hair off the
  stop and stop, rather than grinding through the whole settle timeout;
- **retry inquiries** so a momentarily-busy MCU doesn't read as "no data";
- move **pan/tilt and zoom concurrently** (both commands fire, then wait for both).

Don't hand-position the camera (the motor fights it) — drive it with `ptz`.

## Utilities

Function-type utils (sourced, so they work via `xsh <lib>/<util>` without needing
`/usr/local/bin`). The real logic is a single stdlib-`python3` core in `libexec/`
(no pyserial / no venv), shared by the utils and by the bare PATH commands.

```
xsh hellocore/ptz/zoom [0-100 | 0xNNNN | wide | tele]
xsh hellocore/ptz/move [P [T [Z]]] | [pan P] [tilt T] [zoom Z] | center | reset
```

`reset` runs the camera's own calibration (VISCA `06 05`) back to (0,0) without
grinding — the right recovery after the gimbal has been hand-moved or confused
(`center` is a quick absolute move to 0,0 for when it's already well-referenced).

Pan/tilt are signed **percent of range** (−100…100), zoom is 0…100 (or
`wide`/`tele`). Positional `move P T Z` and keyword forms both work. Prefix a
value with `=` for a raw VISCA unit. Port override: `$XSH_HELLOCORE_PORT`
(default `/dev/cu.usbserial-1110`).

### Bare `zoom` / `ptz` on PATH

`xsh imports` links to `/usr/local/bin` and names commands `<lib>-<pkg>-<util>`,
which is unwritable on Apple Silicon and not the names we want. Instead the two
core scripts are symlinked into `~/.local/bin` (already on PATH), so `zoom` and
`ptz` work from any shell, OBS, or cron:

```sh
ln -sfn ~/.xsh/lib/hellocore/libexec/zoom ~/.local/bin/zoom
ln -sfn ~/.xsh/lib/hellocore/libexec/ptz  ~/.local/bin/ptz
```

```
zoom 60                      # optical zoom to 60%
ptz pan 40 tilt -15 zoom 30  # aim + zoom
ptz 50 -40 30                # same, positional
ptz center                   # pan/tilt to 0
```

## Test

`bash test.sh` (or `zsh test.sh`) — static checks only (no camera): the CLIs
validate arguments before opening the port, so bad-input and `--help` paths are
covered. CI mirrors alexzhangs/xsh's bash 3.2/4.4/5.x + zsh matrix.

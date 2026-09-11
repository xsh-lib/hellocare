#? Description:
#?   Full pan/tilt/zoom control for the Hellocare PTZ20X2 over its USB VISCA
#?   serial channel (9600 8N1), using VISCA absolute positioning (pan/tilt
#?   06 02, zoom 04 47). Thin wrapper around the lib's stdlib-python core; the
#?   same core backs the bare `ptz` command on PATH (~/.local/bin/ptz).
#?
#?   NOTE: this unit does NOT implement VISCA jog/drive (06 01) or HOME (06 04)
#?   — only absolute/relative positioning and inquiries. `center` therefore
#?   moves to (0,0) via an absolute command, not HOME.
#?
#? Dependency:
#?   1. python3 (stdlib only)
#?   2. Camera USB-serial port. Default /dev/cu.usbserial-1110;
#?      override with $XSH_HELLOCARE_PORT.
#?
#? Usage:
#?   @move [P [T [Z]]]                     positional: pan tilt zoom
#?   @move [pan P] [tilt T] [zoom Z] [focus F]   keyword form (held axes stay)
#?   @move focus F | @move focus auto      manual focus / autofocus (moves nothing else)
#?   @move center                          pan+tilt to 0
#?   @move                                 report current
#?
#?   P, T : -100..100 (percent; -=left/down, +=right/up, 0=center)
#?   Z    : 0..100 | wide | tele ; prefix '=' for a raw VISCA unit
#?   F    : 0..100 (manual focus %) | =raw (0x0000..0x16B4) | auto
#?
#? Return:
#?   0 ok; 1 serial-port error; 2 bad argument.
#?
#? Example:
#?   @move pan 40 tilt -15 zoom 60
#?   @move 50 -40 30
#?   @move center
#?
function move () {
    "${XSH_HOME:-$HOME/.xsh}/lib/hellocare/libexec/ptz" "$@"
}

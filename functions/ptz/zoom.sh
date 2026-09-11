#? Description:
#?   Control the optical zoom of the Hellocare PTZ20X2 over its USB VISCA
#?   serial channel (9600 8N1) using VISCA "Zoom Direct". Thin wrapper around
#?   the lib's stdlib-python core (no pyserial); the same core backs the bare
#?   `zoom` command on PATH (~/.local/bin/zoom).
#?
#? Dependency:
#?   1. python3 (stdlib only)
#?   2. Camera USB-serial port. Default /dev/cu.usbserial-1110;
#?      override with $XSH_HELLOCARE_PORT.
#?
#? Usage:
#?   @zoom [LEVEL]
#?
#? Options:
#?   LEVEL   0-100      Percent of optical range (0=wide/1x, 100=tele/20x).
#?                      Decimals OK (e.g. 55.3) for fine sub-1% steps.
#?           0xNNNN     Raw VISCA position (clamped 0x0118..0x3FE6).
#?           wide|tele  Range ends.
#?           (omitted)  Print current zoom.
#?
#? Return:
#?   0 ok; 1 serial-port error; 2 bad argument.
#?
#? Example:
#?   @zoom            # read
#?   @zoom 60         # 60%
#?   @zoom tele       # 20x
#?
function zoom () {
    "${XSH_HOME:-$HOME/.xsh}/lib/hellocare/libexec/zoom" "$@"
}

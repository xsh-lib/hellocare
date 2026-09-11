#? Description:
#?   Manual focus control for the Hellocare PTZ20X2 over its USB VISCA serial
#?   channel (9600 8N1) using VISCA "Focus Manual" + "Focus Direct". Thin wrapper
#?   around the lib's stdlib-python core (no pyserial); the same core backs the
#?   bare `focus` command on PATH (~/.local/bin/focus).
#?
#?   The unit's autofocus hunts/drifts (worse with a close-up lens), so locking a
#?   manual focus position gives a stable focus for a fixed working distance.
#?
#? Dependency:
#?   1. python3 (stdlib only)
#?   2. Camera USB-serial port (auto-detected; override with $XSH_HELLOCARE_PORT).
#?
#? Usage:
#?   @focus [LEVEL]
#?
#? Options:
#?   LEVEL   0-100      Percent of manual-focus travel (switches to Focus Manual).
#?           0xNNNN     Raw VISCA focus position (clamped 0x0000..0x16B4).
#?           auto       Restore autofocus.
#?           (omitted)  Print current focus.
#?
#? Return:
#?   0 ok; 1 serial-port error; 2 bad argument.
#?
#? Example:
#?   @focus           # read
#?   @focus 55        # lock manual focus at 55%
#?   @focus auto      # back to autofocus
#?
function focus () {
    "${XSH_HOME:-$HOME/.xsh}/lib/hellocare/libexec/focus" "$@"
}

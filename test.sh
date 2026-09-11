#!/bin/bash
#
# Tests for xsh-lib/hellocare. Plain assertions, no external framework (mirrors
# xsh-lib/rigol/test.sh). Runs under bash and zsh.
#
# Static checks only — they do NOT touch a real camera (CI has none). The CLIs
# parse and validate arguments BEFORE opening the serial port, so bad-argument
# and --help paths exercise real code with no hardware. They verify the library
# loads, every utility is listed / exposes help, and argument parsing rejects
# bad input.
#
# Usage:
#   xsh load xsh-lib/core <user>/hellocare   # one-time
#   bash test.sh                             # or: zsh test.sh
#

# Make `xsh` available as a function when run as a child process.
if ! type xsh 2>/dev/null | grep -q 'function'; then
    # shellcheck source=/dev/null
    . ~/.xshrc
fi

set -e -o pipefail

__dir=$(cd "$(dirname "$0")" && pwd)
__lib=$(awk -F= '/^name=/{print $2; exit}' "$__dir/xsh.lib")
[ -n "$__lib" ] || { echo "test.sh: could not read library name from xsh.lib" >&2; exit 1; }

xsh log info "xsh list ${__lib}/"
xsh list "${__lib}/*" >/dev/null

# Every utility must be listable and expose help metadata.
for util in ptz/zoom ptz/focus ptz/move; do
    xsh log info "help: ${__lib}/${util}"
    xsh help "${__lib}/${util}" >/dev/null
done

# --help must succeed (exit 0) and needs no camera.
xsh "${__lib}/ptz/zoom" --help >/dev/null
xsh "${__lib}/ptz/focus" --help >/dev/null
xsh "${__lib}/ptz/move" --help >/dev/null

# Argument validation: bad input must fail (non-zero), with no port access.
if xsh "${__lib}/ptz/zoom" not-a-level >/dev/null 2>&1; then
    echo "test.sh: ptz/zoom accepted a bad level" >&2; exit 1
fi
if xsh "${__lib}/ptz/zoom" 10 20 >/dev/null 2>&1; then
    echo "test.sh: ptz/zoom accepted too many arguments" >&2; exit 1
fi
if xsh "${__lib}/ptz/focus" not-a-level >/dev/null 2>&1; then
    echo "test.sh: ptz/focus accepted a bad level" >&2; exit 1
fi
if xsh "${__lib}/ptz/focus" 10 20 >/dev/null 2>&1; then
    echo "test.sh: ptz/focus accepted too many arguments" >&2; exit 1
fi
if xsh "${__lib}/ptz/move" bogus-token >/dev/null 2>&1; then
    echo "test.sh: ptz/move accepted a bad positional value" >&2; exit 1
fi
if xsh "${__lib}/ptz/move" pan >/dev/null 2>&1; then
    echo "test.sh: ptz/move accepted a keyword with no value" >&2; exit 1
fi
if xsh "${__lib}/ptz/move" 1 2 3 4 >/dev/null 2>&1; then
    echo "test.sh: ptz/move accepted too many positional values" >&2; exit 1
fi

xsh log info "all hellocare tests passed"

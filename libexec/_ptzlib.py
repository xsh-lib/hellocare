#!/usr/bin/env python3
"""Shared VISCA control core for the Hellocare PTZ20X2 (9600 8N1, camera addr 1).
Pure stdlib (termios) — no pyserial. Imported by the `zoom` and `ptz` CLIs.

Fail-safes for this unit's active position-hold (the motor keeps torque on the
commanded position, so re-commanding a held spot or hitting a stop makes it
grind and blocks the control MCU from answering inquiries):
  * skip a move when already within tolerance of the target,
  * after a move that stalls short of target (mechanical stop), re-issue the
    reached position so the motor stops driving into the stop,
  * retry inquiries so a momentarily-busy MCU doesn't read as "no data".
"""
import os, termios, time, glob

def _autodev():
    # 1) explicit override always wins
    p = os.environ.get("XSH_HELLOCARE_PORT")
    if p:
        return p
    # 2) auto-detect the CH340 USB-serial bridge. macOS names it
    #    /dev/cu.usbserial-<port-location>, so the suffix changes whenever the
    #    cable moves to a different USB port -- glob instead of hard-coding.
    #    (older CH340 kexts expose /dev/cu.wchusbserial* instead.)
    for pat in ("/dev/cu.usbserial-*", "/dev/cu.wchusbserial*", "/dev/cu.usbserial*"):
        cands = sorted(glob.glob(pat))
        if cands:
            return cands[0]
    # 3) last-resort default (keeps a clear error message if nothing is plugged)
    return "/dev/cu.usbserial-1110"

DEV = _autodev()

# --- command envelope of this unit (VISCA units) -------------------------
# The firmware clamps BOTH absolute (06 02) AND relative (06 03) targets to one
# soft-limit window — there is NO command path past it (jog 06 01 is
# unimplemented), so these ARE the reachable command limits. They sit well
# inside the true physical travel (pan ~360°, tilt ~180°+, reachable only by
# hand), so commanding the edge parks the servo there cleanly — no stop, no
# grind. ±100% maps to these edges.
WIDE, TELE         = 0x0118, 0x3FE6      # 1x .. 20x
PAN_MIN, PAN_MAX   = -2018, 2147         # firmware soft-limit window (measured)
TILT_MIN, TILT_MAX = -576, 1200          # firmware soft-limit window (measured)
# -------------------------------------------------------------------------
PAN_SPD, TILT_SPD = 0x10, 0x10
PT_SKIP_TOL, PT_REACH_TOL, ZOOM_TOL = 3, 6, 0x08  # skip-if-there / reached / zoom tol
# ZOOM_TOL kept small (8 units ~0.05%) so fine float-percent steps aren't skipped
# (zoom is a plain lens motor, not the position-hold servo, so re-commanding a
#  near-identical zoom doesn't grind).
STALL_POLLS = 3                          # no-progress polls before declaring a stall
FOCUS_MIN, FOCUS_MAX = 0x0000, 0x16B4    # manual-focus travel (measured; higher clamps)
# tilt/pan 1% = 12/21 units, so the skip tol must be small or small steps vanish.

def sopen(dev=DEV):
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)                       # [if,of,cf,lf,isp,osp,cc]
    a[0] = 0; a[1] = 0; a[3] = 0                     # raw
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = termios.B9600; a[5] = termios.B9600
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd

def _frames(fd, t):
    end = time.time() + t; buf = bytearray(); out = []
    while time.time() < end:
        try: d = os.read(fd, 64)
        except OSError: d = b""
        if d:
            buf += d
            while 0xFF in buf:
                i = buf.index(0xFF); out.append(bytes(buf[:i+1])); del buf[:i+1]
        else: time.sleep(0.02)
    return out

def _sgn(v): return v - 0x10000 if v > 0x7fff else v
def _nib(v):
    v &= 0xFFFF; return [(v>>12)&0xF, (v>>8)&0xF, (v>>4)&0xF, v&0xF]

def get_zoom(fd, tries=3):
    for _ in range(tries):
        termios.tcflush(fd, termios.TCIFLUSH); os.write(fd, bytes.fromhex("81090447FF"))
        for f in _frames(fd, 0.8):
            if len(f) == 7 and f[0] == 0x90 and (f[1] >> 4) == 0x5:
                return (f[2]&0xF)<<12 | (f[3]&0xF)<<8 | (f[4]&0xF)<<4 | (f[5]&0xF)
        time.sleep(0.15)
    return None

def get_pt(fd, tries=3):
    for _ in range(tries):
        termios.tcflush(fd, termios.TCIFLUSH); os.write(fd, bytes.fromhex("81090612FF"))
        for f in _frames(fd, 0.8):
            if len(f) == 11 and f[0] == 0x90 and (f[1] >> 4) == 0x5:
                pan = (f[2]&0xF)<<12 | (f[3]&0xF)<<8 | (f[4]&0xF)<<4 | (f[5]&0xF)
                til = (f[6]&0xF)<<12 | (f[7]&0xF)<<8 | (f[8]&0xF)<<4 | (f[9]&0xF)
                return _sgn(pan), _sgn(til)
        time.sleep(0.15)
    return None

def _zoom_cmd(fd, pos):
    p = _nib(pos)
    termios.tcflush(fd, termios.TCIOFLUSH)
    os.write(fd, bytes([0x81,0x01,0x04,0x47, p[0],p[1],p[2],p[3], 0xFF]))
    _frames(fd, 0.5)

def set_zoom(fd, pos, settle=6.0):
    pos = max(WIDE, min(TELE, pos))
    cur = get_zoom(fd)
    if cur is not None and abs(cur - pos) <= ZOOM_TOL:      # already there: skip
        return
    _zoom_cmd(fd, pos)
    end = time.time() + settle; last = None
    while time.time() < end:
        cur = get_zoom(fd)
        if cur is not None and last is not None and abs(cur - last) < 0x30: break
        last = cur; time.sleep(0.25)

def _pt_cmd(fd, pan, til):
    b = [0x81,0x01,0x06,0x02, PAN_SPD, TILT_SPD] + _nib(pan) + _nib(til) + [0xFF]
    termios.tcflush(fd, termios.TCIOFLUSH); os.write(fd, bytes(b))
    _frames(fd, 0.5)

def set_pt(fd, pan, til, settle=10.0):
    pan = max(PAN_MIN, min(PAN_MAX, pan)); til = max(TILT_MIN, min(TILT_MAX, til))
    cur = get_pt(fd)
    if cur and abs(cur[0]-pan) <= PT_SKIP_TOL and abs(cur[1]-til) <= PT_SKIP_TOL:  # already there
        return
    _pt_cmd(fd, pan, til)
    end = time.time() + settle; last = None
    while time.time() < end:
        cur = get_pt(fd)
        if cur and last and abs(cur[0]-last[0]) < 4 and abs(cur[1]-last[1]) < 4: break
        last = cur; time.sleep(0.3)
    # Fail-safe: if it stalled short of target (hit a mechanical stop), re-issue
    # the position it actually reached so the motor stops driving into the stop.
    final = get_pt(fd)
    if final and (abs(final[0]-pan) > PT_REACH_TOL or abs(final[1]-til) > PT_REACH_TOL):
        _pt_cmd(fd, final[0], final[1]); _frames(fd, 0.3)

def move(fd, pan=None, til=None, zoom=None, timeout=12.0):
    """Move pan/tilt and zoom CONCURRENTLY (both commands fire, then we wait for
    both). Skips an axis already on target. Detects a pan/tilt STALL early — if
    the position stops progressing toward target (a mechanical/soft stop, e.g.
    after a hand-move pushed it past the addressable window) it re-commands a
    hair off the stop and stops, instead of grinding through the whole timeout."""
    if pan  is not None: pan  = max(PAN_MIN,  min(PAN_MAX,  pan))
    if til  is not None: til  = max(TILT_MIN, min(TILT_MAX, til))
    if zoom is not None: zoom = max(WIDE,     min(TELE,     zoom))
    cur_pt = get_pt(fd); cur_z = get_zoom(fd)
    tp = pan if pan is not None else (cur_pt[0] if cur_pt else 0)
    tt = til if til is not None else (cur_pt[1] if cur_pt else 0)
    pt_need = (pan is not None or til is not None)
    if pt_need and cur_pt and abs(cur_pt[0]-tp) <= PT_SKIP_TOL and abs(cur_pt[1]-tt) <= PT_SKIP_TOL:
        pt_need = False
    z_need = (zoom is not None) and not (cur_z is not None and abs(cur_z-zoom) <= ZOOM_TOL)
    if pt_need: _pt_cmd(fd, tp, tt)          # fire both together -> concurrent motion
    if z_need:  _zoom_cmd(fd, zoom)
    end = time.time() + timeout; best = None; stalls = 0
    while (pt_need or z_need) and time.time() < end:
        if pt_need:
            c = get_pt(fd)
            if c:
                dist = abs(c[0]-tp) + abs(c[1]-tt)
                if dist <= 2*PT_REACH_TOL:                  # reached
                    pt_need = False
                elif best is None or dist < best - 4:      # still progressing
                    best = dist; stalls = 0
                else:                                       # not progressing
                    stalls += 1
                    if stalls >= STALL_POLLS:               # stuck (stop/desync) -> stop driving, hold here
                        _pt_cmd(fd, c[0], c[1]); _frames(fd, 0.3)
                        pt_need = False
        if z_need:
            c = get_zoom(fd)
            if c is not None and abs(c-zoom) <= 2*ZOOM_TOL:
                z_need = False
        time.sleep(0.12)

def reset(fd, timeout=25.0):
    """Trigger the camera's own Pan-Tilt calibration (VISCA Pan-Tilt Reset,
    81 01 06 05) — the clean, grind-free absolute re-referencing it also runs on
    power-on. Ends centered at (0,0); takes ~15-20s. This is the correct recovery
    when the gimbal has been hand-moved / confused, since it re-establishes the
    absolute reference without driving blindly into a stop. Returns final pos."""
    termios.tcflush(fd, termios.TCIOFLUSH)
    os.write(fd, bytes.fromhex("81010605FF"))
    _frames(fd, 1.0)                       # consume ACK/DONE
    t0 = time.time(); last = None; stable = None
    while time.time() - t0 < timeout:      # wait out the calibration (MCU busy)
        p = get_pt(fd)
        if p is not None:
            if last and abs(p[0]-last[0]) < 6 and abs(p[1]-last[1]) < 6:
                if stable is None: stable = time.time()
                elif time.time() - stable > 1.0: return p
            else: stable = None
            last = p
        time.sleep(0.4)
    return get_pt(fd)

def pan_pct(u):  return round(u / (PAN_MAX if u >= 0 else -PAN_MIN) * 100)
def tilt_pct(u): return round(u / (TILT_MAX if u >= 0 else -TILT_MIN) * 100)
def zoom_pct(u): return round((u - WIDE) / (TELE - WIDE) * 100)
def pan_u(p):    return round(p/100 * (PAN_MAX if p >= 0 else -PAN_MIN))
def tilt_u(p):   return round(p/100 * (TILT_MAX if p >= 0 else -TILT_MIN))
def zoom_u(p):   return int(WIDE + (TELE - WIDE) * p / 100)
def focus_pct(u): return round((u - FOCUS_MIN) / (FOCUS_MAX - FOCUS_MIN) * 100)
def focus_u(p):   return int(FOCUS_MIN + (FOCUS_MAX - FOCUS_MIN) * p / 100)

# --- manual focus (VISCA Focus Auto/Manual 04 38, Focus Direct 04 48) ---------
# The unit's autofocus hunts / drifts (esp. with a close-up lens), so manual
# focus is the way to a stable, locked focus point. Range measured 0x0000..0x16B4.
def get_focus(fd, tries=3):
    for _ in range(tries):
        termios.tcflush(fd, termios.TCIFLUSH); os.write(fd, bytes.fromhex("81090448FF"))
        for f in _frames(fd, 0.8):
            if len(f) == 7 and f[0] == 0x90 and (f[1] >> 4) == 0x5:
                return (f[2]&0xF)<<12 | (f[3]&0xF)<<8 | (f[4]&0xF)<<4 | (f[5]&0xF)
        time.sleep(0.15)
    return None

def focus_auto(fd):                       # restore autofocus
    os.write(fd, bytes.fromhex("8101043802FF")); _frames(fd, 0.5)

def set_focus(fd, pos):                   # lock manual focus at absolute position
    pos = max(FOCUS_MIN, min(FOCUS_MAX, pos))
    os.write(fd, bytes.fromhex("8101043803FF")); _frames(fd, 0.4)   # Focus Manual
    n = _nib(pos)
    os.write(fd, bytes([0x81,0x01,0x04,0x48] + n + [0xFF])); _frames(fd, 0.5)
    return pos

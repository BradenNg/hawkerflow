"""Generate a square duct pipe (5 cm x 5 cm) with a mounting flange for the hood.

Edit the parameters below and re-run:  python hood_pipe.py
Output: hood_pipe.stl (units: mm)
"""
import struct

# ---- Parameters (mm) ----
OUTER = 50.0         # outer width of the square pipe (5 cm)
WALL = 2.0           # wall thickness
HEIGHT = 60.0        # total height, including flange
FLANGE_W = 70.0      # flange outer width (sits on top of the hood); set = OUTER for no flange
FLANGE_T = 3.0       # flange thickness
OUT_FILE = "hood_pipe.stl"


def sq(w, z):
    """Square corners (counter-clockwise viewed from +Z) of width w at height z."""
    h = w / 2
    return [(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)]


tris = []


def quad(a, b, c, d):
    """Add quad a-b-c-d (counter-clockwise when seen from outside)."""
    tris.append((a, b, c))
    tris.append((a, c, d))


def ring(outer, inner, up):
    """Flat square ring between two concentric squares. up=True faces +Z."""
    for i in range(4):
        j = (i + 1) % 4
        if up:
            quad(inner[i], outer[i], outer[j], inner[j])
        else:
            quad(inner[j], outer[j], outer[i], inner[i])


def wall(bot, top, outward):
    """Vertical walls between two squares of equal width."""
    for i in range(4):
        j = (i + 1) % 4
        if outward:
            quad(bot[i], bot[j], top[j], top[i])
        else:
            quad(bot[j], bot[i], top[i], top[j])


inner_w = OUTER - 2 * WALL
fl_t = FLANGE_T if FLANGE_W > OUTER else 0.0

# Bottom face (flange underside, or plain pipe end)
ring(sq(FLANGE_W if fl_t else OUTER, 0), sq(inner_w, 0), up=False)
if fl_t:
    wall(sq(FLANGE_W, 0), sq(FLANGE_W, fl_t), outward=True)   # flange edge
    ring(sq(FLANGE_W, fl_t), sq(OUTER, fl_t), up=True)        # flange top shoulder
wall(sq(OUTER, fl_t), sq(OUTER, HEIGHT), outward=True)        # pipe outer wall
ring(sq(OUTER, HEIGHT), sq(inner_w, HEIGHT), up=True)         # top rim
wall(sq(inner_w, 0), sq(inner_w, HEIGHT), outward=False)      # bore


def normal(a, b, c):
    ux, uy, uz = (b[k] - a[k] for k in range(3))
    vx, vy, vz = (c[k] - a[k] for k in range(3))
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    m = sum(x * x for x in n) ** 0.5 or 1.0
    return tuple(x / m for x in n)


with open(OUT_FILE, "wb") as f:
    f.write(b"hood_pipe 50x50mm square duct".ljust(80, b" "))
    f.write(struct.pack("<I", len(tris)))
    for t in tris:
        f.write(struct.pack("<3f", *normal(*t)))
        for v in t:
            f.write(struct.pack("<3f", *v))
        f.write(b"\x00\x00")

print(f"Wrote {OUT_FILE}: {len(tris)} triangles, "
      f"{OUTER}x{OUTER} mm pipe, {WALL} mm wall, {HEIGHT} mm tall, "
      f"{FLANGE_W}x{FLANGE_W}x{fl_t} mm flange")

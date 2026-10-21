"""
Light Path: a camera ride along a bundle of glowing fibres.

Run in Blender 4.2+ (tested on 5.x):  Scripting tab -> Open this file -> Run Script.
The script builds a fresh scene called "LightPath" (re-running rebuilds it):

  * a ribbon of thin light fibres, wide at the back, arcing up over a crest
    and diving down to a single point (the tip), with tiny "dew" sparkles
  * an animated material: light pulses run along the fibres towards the tip,
    plus a slow shimmer noise
  * a lavender / deep-navy gradient world that fades to black at the end
  * a camera that rides forward on top of the ribbon (never backwards, never
    through it), follows it up over the crest and looks down the dive, then
    lifts off to see the whole shape from the side

Storyboard (reference frames). The camera never goes through the fibres:
  K1  ref 2 - macro, riding just above the fibres, they stream past
  K2  ref 1 - riding up the arc, the ribbon curves over ahead of the camera
  K3  ref 3 - over the crest: the camera looks down along the dive to the tip
  K4  ref 4 - lift off: the camera flies away from the ribbon and looks back at
              it, fan on the left, tip in the centre, background fades to black

Tweak everything in the CONFIG block and CAMERA_KEYS, then run again.
"""

import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
SCENE_NAME = "LightPath"
ENGINE = "EEVEE"            # "EEVEE" (fast) or "CYCLES" (slower, a bit richer)
FPS = 24
FRAME_END = 288             # 12 s
RES_X, RES_Y = 1920, 1080
SEED = 7

# Path / fibre bundle
PATH_LENGTH = 30.0          # length from the back of the fan to the tip (along +X)
PITCH_BACK = 35.0           # the ribbon rises at this angle at the back (degrees)...
PITCH_TIP = -75.0           # ...goes over a crest and dives down at this angle to the tip
BEND_START = 0.25           # where along the path the arc starts (0 = back, 1 = tip)
BEND_END = 0.75             # ... and where it ends
FAN_RADIUS = 6.0            # half-width of the fan at the very back
FAN_THICKNESS = 0.05        # ribbon thickness relative to its width
FAN_CURL = 0.12             # edges of the ribbon lift a little (shallow channel)
FAN_TWIST = 0.0             # twist of the ribbon along the path (radians)
CONVERGE_POWER = 2.3        # >1 gives the concave "cusp" shape near the tip
TAIL_LENGTH = 0.6           # thin line continuing past the convergence point
STRAND_COUNT = 6000
STRAND_POINTS = 72
STRAND_RADIUS = 0.0025
DEW_COUNT = 30000

# Look
COLOR_FIBRE = (0.86, 0.88, 1.0)
COLOR_FIBRE_DIM = (0.42, 0.46, 0.75)
COLOR_SKY_GLOW = (0.80, 0.80, 0.93)
COLOR_SKY_MID = (0.26, 0.26, 0.50)
COLOR_SKY_DARK = (0.006, 0.007, 0.022)
COLOR_SKY_NAVY = (0.03, 0.03, 0.09)
FIBRE_EMISSION = 1.3        # base glow of the fibres
FIBRE_OPACITY = 0.35        # fibres are see-through, so dense areas glow brighter
PULSE_STRENGTH = 6.0        # extra glow of the travelling light pulses
PULSE_SPEED = 0.22          # pulses per second along a fibre
SHIMMER_SPEED = 0.25        # how fast the shimmer noise evolves
GLOW_DIRECTION = (0.5, 0.2, 0.85)  # where the lavender light sits in the sky
WORLD_FADE_START = 185      # frame where the background starts fading to black
WORLD_FADE_END = 240        # frame where it is fully black

# Camera. Positions are given relative to the ribbon, so the camera follows it:
#   s       - where along the path the camera is (0 = back of the fan, 1 = tip)
#   up      - height above the ribbon (the camera never goes below or through it:
#             it is pushed up automatically to keep CAMERA_CLEARANCE)
#   side    - offset across the ribbon
#   look_s  - which point of the path the camera looks at
#   look_up / look_side - offsets of that look-at point
#   lens    - focal length in mm, roll in degrees
#   up_b    - 0: the top of the frame points away from the ribbon (riding on it);
#             1 / -1: the top of the frame points across the ribbon (side view)
# Values are blended with a smooth monotone curve, so the camera never stops
# or reverses between keys.
CAMERA_KEYS = [
    # Ride forward on top of the ribbon, up the arc, over the crest, down the dive, lift off.
    # frame   s     up    side  look_s look_up look_side lens  roll  up_b
    dict(frame=1,   s=0.04, up=0.3,  side=0.4, look_s=0.14,  look_up=0.0, look_side=0.9, lens=35, roll=25,  up_b=0),  # K1 ref 2
    dict(frame=95,  s=0.30, up=1.0,  side=0.0, look_s=0.50,  look_up=2.0, look_side=0.0, lens=24, roll=0,   up_b=0),  # K2 ref 1
    dict(frame=175, s=0.58, up=3.0,  side=0.0, look_s=1.00,  look_up=0.0, look_side=0.0, lens=24, roll=-20, up_b=0),  # K3 ref 3
    dict(frame=250, s=0.50, up=25.0, side=0.0, look_s=0.72,  look_up=0.0, look_side=0.0, lens=30, roll=0,   up_b=1),  # K4 ref 4
    dict(frame=288, s=0.50, up=27.0, side=0.0, look_s=0.725, look_up=0.0, look_side=0.0, lens=30, roll=0,   up_b=1),  # hold, drift away
]
CAMERA_CLEARANCE = 0.12     # minimum distance between the camera and any fibre
MOTION_BLUR = 0.5           # shutter length in frames, 0 disables the streaks
DOF_FSTOP = 2.8             # lower = shallower depth of field (only near K1)


# --------------------------------------------------------------------------
# Path geometry
# --------------------------------------------------------------------------
def bend_angle(s):
    """Pitch of the path at s: rising at the back, arcing over a crest, diving to the tip."""
    k = np.clip((np.asarray(s, dtype=float) - BEND_START) / (BEND_END - BEND_START), 0.0, 1.0)
    k = k * k * (3 - 2 * k)
    return np.radians(PITCH_BACK + (PITCH_TIP - PITCH_BACK) * k)


_SPINE = {}


def spine(s):
    """Centre line of the ribbon (an arc in the XZ plane). s may be an array; s=1 is the tip."""
    if not _SPINE:
        grid = np.linspace(-0.5, 1.5, 8001)
        theta = bend_angle(grid)
        step = PATH_LENGTH * (grid[1] - grid[0])
        x = np.cumsum(np.cos(theta)) * step
        z = np.cumsum(np.sin(theta)) * step
        i0 = np.searchsorted(grid, 0.0)
        _SPINE.update(grid=grid, x=x - x[i0], z=z - z[i0])
    s = np.asarray(s, dtype=float)
    x = np.interp(s, _SPINE["grid"], _SPINE["x"])
    z = np.interp(s, _SPINE["grid"], _SPINE["z"])
    return np.stack([x, np.zeros_like(x), z], axis=-1)


def spine_frame(s):
    """Tangent, side (across the ribbon) and up (away from the ribbon) unit vectors."""
    theta = bend_angle(s)
    c, sn = np.cos(theta), np.sin(theta)
    zero = np.zeros_like(c)
    t = np.stack([c, zero, sn], axis=-1)
    side = np.stack([zero, zero + 1.0, zero], axis=-1)
    up = np.stack([-sn, zero, c], axis=-1)
    return t, side, up


def fan_radius(s):
    back = np.clip(1.0 - np.asarray(s, dtype=float), 0.0, None)
    return FAN_RADIUS * back ** CONVERGE_POWER + 0.004


def path_point(s, side=0.0, up=0.0):
    _, sd, u = spine_frame(np.array([s]))
    p = spine(np.array([s]))[0] + sd[0] * side + u[0] * up
    return Vector(p.tolist())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def engine_id(name):
    if name.upper() == "CYCLES":
        return "CYCLES"
    items = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in items else "BLENDER_EEVEE"


def new_scene():
    old = bpy.data.scenes.get(SCENE_NAME)
    if old:
        for ob in list(old.collection.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        if len(bpy.data.scenes) == 1:
            bpy.data.scenes.new("Scene")
        bpy.data.scenes.remove(old)
    scene = bpy.data.scenes.new(SCENE_NAME)
    if bpy.context.window:
        bpy.context.window.scene = scene
    return scene


def link(scene, ob):
    scene.collection.objects.link(ob)
    return ob


def node(nt, kind, loc=(0, 0), **inputs):
    n = nt.nodes.new(kind)
    n.location = loc
    for key, val in inputs.items():
        n.inputs[key].default_value = val
    return n


def math_node(nt, op, a=None, b=None, loc=(0, 0), clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.location = loc
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def time_value(nt, loc=(-1400, 0)):
    """A Value node driven by the frame number (seconds)."""
    v = nt.nodes.new("ShaderNodeValue")
    v.label = "Time (s)"
    v.location = loc
    fc = v.outputs[0].driver_add("default_value")
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = f"frame / {FPS}"
    return v.outputs[0]


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
def fibre_material():
    mat = bpy.data.materials.new("Fibre Light")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (900, 0))
    info = node(nt, "ShaderNodeHairInfo", (-1400, 300))
    t = time_value(nt)

    # Travelling pulses: bright bands that run along each fibre to the tip.
    phase = math_node(nt, "MULTIPLY", info.outputs["Random"], 9.0, (-1150, 400))
    x = math_node(nt, "MULTIPLY_ADD", info.outputs["Intercept"], 2.5, (-1150, 250))
    nt.links.new(phase, x.node.inputs[2])
    tt = math_node(nt, "MULTIPLY", t, PULSE_SPEED * 2.5, (-1150, 100))
    x = math_node(nt, "SUBTRACT", x, tt, (-950, 250))
    x = math_node(nt, "MULTIPLY", x, 2 * math.pi, (-800, 250))
    x = math_node(nt, "SINE", x, None, (-650, 250))
    x = math_node(nt, "MULTIPLY_ADD", x, 0.5, (-500, 250))
    x.node.inputs[2].default_value = 0.5
    pulse = math_node(nt, "POWER", x, 14.0, (-350, 250))

    # Per-fibre brightness: most fibres dim, some bright.
    ramp = node(nt, "ShaderNodeValToRGB", (-1150, 650))
    nt.links.new(info.outputs["Random"], ramp.inputs[0])
    ramp.color_ramp.elements[0].color = (0.04, 0.04, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.9
    e = ramp.color_ramp.elements.new(0.6)
    e.color = (0.18, 0.18, 0.18, 1)

    # Shimmer: slow 4D noise drifting through the bundle.
    coord = node(nt, "ShaderNodeNewGeometry", (-1400, -300))
    noise = node(nt, "ShaderNodeTexNoise", (-1150, -250), Scale=0.35, Detail=3.0)
    noise.noise_dimensions = "4D"
    nt.links.new(coord.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(math_node(nt, "MULTIPLY", t, SHIMMER_SPEED, (-1300, -450)), noise.inputs["W"])
    shimmer = math_node(nt, "MULTIPLY_ADD", noise.outputs["Fac"], 1.6, (-900, -250))
    shimmer.node.inputs[2].default_value = -0.3

    # Fade the very back of each fibre in, so the fan has no hard edge.
    fade = math_node(nt, "MULTIPLY", info.outputs["Intercept"], 8.0, (-900, 0), clamp=True)

    bright = math_node(nt, "MULTIPLY", ramp.outputs["Color"], shimmer, (-650, 500))
    bright = math_node(nt, "MULTIPLY", bright, FIBRE_EMISSION, (-500, 500))
    pulse_s = math_node(nt, "MULTIPLY", pulse, PULSE_STRENGTH, (-200, 250))
    pulse_s = math_node(nt, "MULTIPLY", pulse_s, ramp.outputs["Color"], (-50, 250))
    strength = math_node(nt, "ADD", bright, pulse_s, (100, 400))
    strength = math_node(nt, "MULTIPLY", strength, fade, (250, 400))

    col = node(nt, "ShaderNodeMix", (100, 0))
    col.data_type = "RGBA"
    nt.links.new(noise.outputs["Fac"], col.inputs["Factor"])
    col.inputs[6].default_value = (*COLOR_FIBRE_DIM, 1)
    col.inputs[7].default_value = (*COLOR_FIBRE, 1)

    emit = node(nt, "ShaderNodeEmission", (450, 100))
    nt.links.new(col.outputs[2], emit.inputs["Color"])
    nt.links.new(strength, emit.inputs["Strength"])
    transp = node(nt, "ShaderNodeBsdfTransparent", (450, -100))
    mix = node(nt, "ShaderNodeMixShader", (700, 0))
    nt.links.new(math_node(nt, "MULTIPLY", fade, FIBRE_OPACITY, (550, 250)), mix.inputs[0])
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(emit.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def dew_material():
    mat = bpy.data.materials.new("Dew Sparkle")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (700, 0))
    info = node(nt, "ShaderNodeObjectInfo", (-900, 200))
    t = time_value(nt, (-900, -100))
    # Each sparkle twinkles at its own phase.
    x = math_node(nt, "MULTIPLY_ADD", t, 3.0, (-650, 0))
    nt.links.new(math_node(nt, "MULTIPLY", info.outputs["Random"], 40.0, (-800, 300)), x.node.inputs[2])
    x = math_node(nt, "SINE", x, None, (-450, 0))
    x = math_node(nt, "MULTIPLY_ADD", x, 0.5, (-300, 0))
    x.node.inputs[2].default_value = 0.5
    tw = math_node(nt, "POWER", x, 3.0, (-150, 0))
    s = math_node(nt, "MULTIPLY_ADD", tw, 9.0, (0, 0))
    s.node.inputs[2].default_value = 1.5
    emit = node(nt, "ShaderNodeEmission", (300, 0), Color=(*COLOR_FIBRE, 1))
    nt.links.new(s, emit.inputs["Strength"])
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def build_world(scene):
    world = bpy.data.worlds.new("Light Path Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputWorld", (900, 0))
    tc = node(nt, "ShaderNodeTexCoord", (-900, 0))

    # Glow lobe ahead of the tip and above it; dark everywhere else.
    glow_dir = Vector(GLOW_DIRECTION).normalized()
    dot = node(nt, "ShaderNodeVectorMath", (-650, 0))
    dot.operation = "DOT_PRODUCT"
    nt.links.new(tc.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = glow_dir
    ramp = node(nt, "ShaderNodeValToRGB", (-400, 0))
    nt.links.new(dot.outputs["Value"], ramp.inputs[0])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.15, (*COLOR_SKY_DARK, 1)
    els[1].position, els[1].color = 1.0, (*COLOR_SKY_GLOW, 1)
    for pos, c in ((0.55, COLOR_SKY_NAVY), (0.85, COLOR_SKY_MID)):
        els.new(pos).color = (*c, 1)

    bg = node(nt, "ShaderNodeBackground", (300, 0))
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    black = node(nt, "ShaderNodeBackground", (300, -200), Color=(0, 0, 0, 1))
    mix = node(nt, "ShaderNodeMixShader", (600, 0))
    mix.label = "Fade to black"
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(black.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])

    fac = mix.inputs[0]
    for frame, val in ((WORLD_FADE_START, 0.0), (WORLD_FADE_END, 1.0)):
        fac.default_value = val
        fac.keyframe_insert("default_value", frame=frame)
    fac.default_value = 0.0


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def strand_positions(rng):
    n, m = STRAND_COUNT, STRAND_POINTS
    tail = TAIL_LENGTH / PATH_LENGTH
    # Fibres start at slightly different places at the back.
    start = rng.uniform(0.0, 0.12, n)
    u = np.linspace(0.0, 1.0, m)
    s = start[:, None] + (1.0 + tail - start[:, None]) * u[None, :] ** 0.85  # (n, m)

    # Cross-section coordinates: spread evenly across the ribbon's width.
    w = rng.uniform(-1.0, 1.0, n)
    d = rng.normal(0.0, 0.45, n).clip(-1.2, 1.2)

    t, side, up = spine_frame(s)
    r = fan_radius(s)[..., None]
    back = np.clip(1.0 - s, 0.0, None)[..., None]
    twist = FAN_TWIST * back ** 1.5
    cw, sw = np.cos(twist), np.sin(twist)
    axis_w = cw * side + sw * up
    axis_d = -sw * side + cw * up

    wd = w[:, None, None]
    dd = d[:, None, None]
    offset = axis_w * wd + axis_d * (dd * FAN_THICKNESS + FAN_CURL * wd ** 2)

    # Gentle independent wobble per fibre.
    ph = rng.uniform(0, 2 * math.pi, (n, 2))
    fq = rng.uniform(2.0, 5.0, (n, 2))
    wob = 0.012 * (np.sin(fq[:, :1] * s * 2 * math.pi + ph[:, :1])[..., None] * axis_w
                  + np.sin(fq[:, 1:] * s * 2 * math.pi + ph[:, 1:])[..., None] * axis_d)

    pos = spine(s) + r * (offset + wob)
    return pos, s


def build_fibres(scene, rng, mat):
    pos, _ = strand_positions(rng)
    n, m, _ = pos.shape
    hc = bpy.data.hair_curves.new("Fibres")
    hc.add_curves([m] * n)
    hc.position_data.foreach_set("vector", pos.reshape(-1).astype(np.float32))
    rad = hc.attributes.get("radius") or hc.attributes.new("radius", "FLOAT", "POINT")
    taper = np.linspace(1.0, 0.45, m)
    radii = (STRAND_RADIUS * rng.uniform(0.6, 1.4, n)[:, None] * taper[None, :]).astype(np.float32)
    rad.data.foreach_set("value", radii.reshape(-1))
    hc.materials.append(mat)
    ob = bpy.data.objects.new("Fibres", hc)
    return link(scene, ob), pos


def build_dew(scene, rng, pos, mat):
    n, m, _ = pos.shape
    # Pick random points along fibres, biased towards the wide part.
    ci = rng.integers(0, n, DEW_COUNT)
    pi = (rng.uniform(0, 1, DEW_COUNT) ** 1.4 * (m - 2)).astype(int) + 1
    pts = pos[ci, pi] + rng.normal(0, 0.004, (DEW_COUNT, 3))
    obs = []
    for name, size, frac in (("Dew Small", 0.004, 0.8), ("Dew Big", 0.008, 0.2)):
        k = int(DEW_COUNT * frac)
        sel, pts = pts[:k], pts[k:]
        me = bpy.data.meshes.new(name + " Points")
        me.from_pydata([tuple(p) for p in sel], [], [])
        holder = link(scene, bpy.data.objects.new(name, me))
        holder.instance_type = "VERTS"

        drop = bpy.data.meshes.new(name + " Drop")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size)
        bm.to_mesh(drop)
        bm.free()
        drop.materials.append(mat)
        child = link(scene, bpy.data.objects.new(name + " Drop", drop))
        child.parent = holder
        obs.append(holder)
    return obs


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
def monotone_cubic(xs, ys):
    """Fritsch-Carlson interpolation: smooth, never overshoots, never stops early."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    h = np.diff(xs)
    delta = np.diff(ys) / h
    m = np.zeros_like(ys)
    m[0], m[-1] = delta[0], delta[-1]
    for i in range(1, len(ys) - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])

    def f(x):
        i = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


def clearance_push(eye, normal, pts, clearance):
    """How far to lift the camera along the ribbon normal so no fibre is closer than clearance."""
    push = 0.0
    box = pts[np.all(np.abs(pts - eye) < clearance + 2.0, axis=1)]
    for _ in range(30):
        if len(box) == 0:
            break
        dmin = np.sqrt(((box - (eye + normal * push)) ** 2).sum(axis=1).min())
        if dmin >= clearance:
            break
        push += clearance - dmin + 0.005
    return push


def camera_pose(v, push=0.0):
    """Camera position, look-at point and rotation for one set of key values."""
    _, sd, n = spine_frame(np.array([v["s"]]))
    eye = path_point(v["s"], v["side"], v["up"] + push)
    target = path_point(v["look_s"], v["look_side"], v["look_up"])
    forward = (target - eye).normalized()
    ub = v["up_b"]
    up_hint = Vector(n[0]) * (1 - abs(ub)) + Vector(sd[0]) * ub
    right = forward.cross(up_hint).normalized()
    up = right.cross(forward)
    q = Matrix((right, up, -forward)).transposed().to_quaternion()
    q = q @ Quaternion((0, 0, 1), math.radians(v["roll"]))
    return eye, target, q


def build_camera(scene, fibre_pos):
    cam_data = bpy.data.cameras.new("Rider")
    cam_data.sensor_width = 36
    cam_data.clip_start = 0.01
    cam_data.clip_end = 500
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = DOF_FSTOP
    cam = link(scene, bpy.data.objects.new("Rider Camera", cam_data))
    cam.rotation_mode = "QUATERNION"
    scene.camera = cam

    focus = link(scene, bpy.data.objects.new("Focus Target", None))
    focus.empty_display_size = 0.3
    cam_data.dof.focus_object = focus

    frames = [k["frame"] for k in CAMERA_KEYS]
    chans = {c: monotone_cubic(frames, [k[c] for k in CAMERA_KEYS])
             for c in ("s", "side", "up", "look_s", "look_side", "look_up", "lens", "roll", "up_b")}
    span = range(scene.frame_start, scene.frame_end + 1)
    vals = [{c: float(fn(f)) for c, fn in chans.items()} for f in span]

    # Keep the camera outside the ribbon: lift it where it would touch fibres,
    # then smooth the lift so it reads as a natural move, not a bump.
    pts = fibre_pos[:, ::2].reshape(-1, 3)
    pushes = []
    for v in vals:
        _, _, n = spine_frame(np.array([v["s"]]))
        eye = np.array(path_point(v["s"], v["side"], v["up"]))
        pushes.append(clearance_push(eye, n[0], pts, CAMERA_CLEARANCE))
    pushes = np.array(pushes)
    pushes = np.array([pushes[max(0, i - 6):i + 7].max() for i in range(len(pushes))])
    kernel = np.exp(-0.5 * (np.arange(-12, 13) / 4.0) ** 2)
    pushes = np.convolve(np.pad(pushes, 12, mode="edge"), kernel / kernel.sum(), mode="valid")

    prev = None
    for f, v, push in zip(span, vals, pushes):
        eye, target, q = camera_pose(v, push)
        if prev is not None and prev.dot(q) < 0:
            q.negate()
        prev = q
        cam.location = eye
        cam.rotation_quaternion = q
        cam_data.lens = v["lens"]
        # Focus on the fibres just ahead early on, on the look-at point later.
        near = path_point(min(v["s"] + 0.05, 1.0), v["look_side"] * 0.5, 0)
        focus.location = near.lerp(target, min(1.0, max(0.0, (f - 1) / 150)))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_quaternion", frame=f)
        cam_data.keyframe_insert("lens", frame=f)
        focus.keyframe_insert("location", frame=f)
    # DOF opens up as the camera leaves the fibres.
    cam_data.dof.aperture_fstop = DOF_FSTOP
    cam_data.dof.keyframe_insert("aperture_fstop", frame=1)
    cam_data.dof.aperture_fstop = 16
    cam_data.dof.keyframe_insert("aperture_fstop", frame=150)
    return cam


# --------------------------------------------------------------------------
# Render settings / glow
# --------------------------------------------------------------------------
def setup_render(scene):
    scene.render.engine = engine_id(ENGINE)
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, FRAME_END
    scene.render.resolution_x, scene.render.resolution_y = RES_X, RES_Y
    scene.view_settings.view_transform = "AgX" if "AgX" in [
        e.identifier for e in scene.view_settings.bl_rna.properties["view_transform"].enum_items
    ] else "Filmic"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 128
        scene.cycles.use_denoising = True
    else:
        ee = scene.eevee
        if hasattr(ee, "taa_render_samples"):
            ee.taa_render_samples = 64
    scene.render.film_transparent = False
    # Fibres streak past like in a hyperspace tunnel.
    scene.render.use_motion_blur = MOTION_BLUR > 0
    scene.render.motion_blur_shutter = max(MOTION_BLUR, 0.01)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//render/light_path_"


def setup_glow(scene):
    """Soft bloom in the compositor (API differs between Blender versions)."""
    try:
        if hasattr(scene, "compositing_node_group"):  # Blender 5.0+
            tree = bpy.data.node_groups.new("Light Path Glow", "CompositorNodeTree")
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            scene.compositing_node_group = tree
            out = tree.nodes.new("NodeGroupOutput")
        else:
            scene.use_nodes = True
            tree = scene.node_tree
            tree.nodes.clear()
            out = tree.nodes.new("CompositorNodeComposite")
        rl = tree.nodes.new("CompositorNodeRLayers")
        glare = tree.nodes.new("CompositorNodeGlare")
        rl.location, glare.location, out.location = (-400, 0), (0, 0), (400, 0)
        if "Type" in glare.inputs:
            glare.inputs["Type"].default_value = "Bloom"
            glare.inputs["Threshold"].default_value = 0.8
            glare.inputs["Strength"].default_value = 0.6
            glare.inputs["Size"].default_value = 0.7
        else:
            glare.glare_type = "BLOOM" if "BLOOM" in [
                e.identifier for e in glare.bl_rna.properties["glare_type"].enum_items] else "FOG_GLOW"
            glare.threshold = 0.8
            glare.mix = -0.4
            glare.size = 8
        tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], out.inputs[0])
    except Exception as exc:  # glow is a nice-to-have, never block the scene
        print("Light Path: compositor glow skipped:", exc)


# --------------------------------------------------------------------------
def main():
    rng = np.random.default_rng(SEED)
    random.seed(SEED)
    scene = new_scene()
    setup_render(scene)
    build_world(scene)
    _, pos = build_fibres(scene, rng, fibre_material())
    build_dew(scene, rng, pos, dew_material())
    build_camera(scene, pos)
    setup_glow(scene)
    scene.frame_set(1)
    print("Light Path: scene ready,", STRAND_COUNT, "fibres,", FRAME_END, "frames")


if __name__ == "__main__":
    main()

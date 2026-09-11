"""Surface creation commands."""

from ..core import geometry as g
from .base import NumberReq, PointReq, SelectReq, command


@command("extrude", aliases=("ext", "extrudecrv"))
def cmd_extrude(ctx):
    curves = yield SelectReq("Select curves to extrude", kinds=("curve",),
                             edges_as_curves=True)
    closed = any(g.is_closed_curve(c.shape) for c in curves)
    direction = tuple(ctx.cplane.normal)

    def _make(dist, cap):
        both = ctx.opt("BothSides", "No") == "Yes"
        shapes = []
        for c in curves:
            shape = c.shape
            if both:
                shape = g.translate(shape,
                                    tuple(-d * dist for d in direction))
            shapes.append(shape)
        return g.extrude_profiles(shapes, direction,
                                  dist * (2 if both else 1), cap=cap)

    choices = {"BothSides": ["No", "Yes"]}
    if closed:
        choices = {"Cap": ["Yes", "No"], **choices}
    base = g.centroid(curves[0].shape)

    def _dist_of(p):
        return sum((c - b) * d for c, b, d in zip(p, base, direction))

    def _preview(p):
        d = _dist_of(p)
        return g.make_compound(_make(d, cap=False)) if abs(d) > 1e-9 \
            else None

    dp = yield PointReq(
        "Extrusion distance (click, or type a number)",
        axis_lock=(base, direction), number_from=(base, direction),
        rubber_from=base, choices=choices,
        default=tuple(b + 10.0 * d for b, d in zip(base, direction)),
        preview_fn=_preview)
    dist = _dist_of(dp)
    if abs(dist) < 1e-9:
        ctx.echo("Zero distance — nothing extruded.")
        return
    cap = closed and ctx.opt("Cap", "Yes") == "Yes"
    both = ctx.opt("BothSides", "No") == "Yes"
    made = [ctx.scene.add(s) for s in _make(dist, cap)]
    if ctx.scene.record_history and not both:
        for result_index, o in enumerate(made):
            ctx.scene.add_record("extrude", [c.id for c in curves], o.id,
                                 direction=list(direction),
                                 dist=float(dist), cap=cap,
                                 result_index=result_index)
    ctx.echo(f"Extruded {len(made)} object(s): "
             + ", ".join(o.name for o in made))


@command("revolve", aliases=("rev",))
def cmd_revolve(ctx):
    curves = yield SelectReq("Select curve to revolve", kinds=("curve",), edges_as_curves=True,
                             max_count=1)
    p1 = yield PointReq("Start of revolve axis")
    p2 = yield PointReq("End of revolve axis", rubber_from=p1)
    angle = yield NumberReq("Angle in degrees", default=360.0)
    axis_dir = tuple(b - a for a, b in zip(p1, p2))
    srf = g.revolve(curves[0].shape, p1, axis_dir, angle)
    obj = ctx.scene.add(srf)
    if ctx.scene.record_history:
        ctx.scene.add_record("revolve", [curves[0].id], obj.id,
                             origin=list(p1), axis=list(axis_dir),
                             angle=float(angle))
    ctx.echo(f"Created {obj.name}.")


@command("loft")
def cmd_loft(ctx):
    curves = yield SelectReq("Select 2 or more profile curves in order",
                             kinds=("curve",), edges_as_curves=True, min_count=2,
                             choices={"Style": ["Normal", "Ruled"]})
    srf = g.loft([c.shape for c in curves],
                 ruled=(ctx.opt("Style", "Normal") == "Ruled"))
    obj = ctx.scene.add(srf)
    if ctx.scene.record_history:
        ctx.scene.add_record("loft", [c.id for c in curves], obj.id,
                             ruled=(ctx.opt("Style", "Normal") == "Ruled"))
    ctx.echo(f"Lofted {len(curves)} curves into {obj.name}.")


@command("planarsrf", aliases=("planar", "planesrf"))
def cmd_planar(ctx):
    """Planar surfaces from curves that close into loops.

    A closed curve, or open curves that meet end to end (four lines
    drawn as a box). A loop inside another on the same plane is a hole.
    """
    curves = yield SelectReq("Select planar curves that close into loops",
                             kinds=("curve",), edges_as_curves=True)
    faces = g.planar_faces_from_curves([c.shape for c in curves])
    made = [ctx.scene.add(f, layer_id=curves[0].layer_id) for f in faces]
    ctx.echo(f"Created {len(made)} planar surface(s).")


@command("sweep1", aliases=("sweep",))
def cmd_sweep1(ctx):
    rails = yield SelectReq("Select rail curve", kinds=("curve",),
                            edges_as_curves=True, max_count=1)
    profiles = yield SelectReq("Select profile curve", kinds=("curve",),
                               edges_as_curves=True, max_count=1,
                               allow_preselected=False)
    srf = g.sweep1(profiles[0].shape, rails[0].shape)
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name}.")


@command("offsetsrf")
def cmd_offsetsrf(ctx):
    objs = yield SelectReq("Select surfaces to offset",
                           kinds=("surface", "solid"))

    from . import dragging
    from .base import PointReq
    # a surface offset runs along its own normal, so that is the way to drag
    origin, normal = g.face_point_normal(g.faces_of(objs[0].shape)[0])
    read = dragging.signed_along(origin, normal)

    def _preview(p):
        d = read(p)
        if abs(d) < 1e-9:
            return None
        try:
            return g.make_compound(
                [g.offset_surface(o.shape, d) for o in objs])
        except g.GeometryError:
            return None

    dp = yield PointReq("Offset distance (click a side, or type a number)",
                        axis_lock=(origin, normal),
                        number_from=(origin, normal),
                        rubber_from=origin, preview_fn=_preview)
    dist = read(dp)
    if abs(dist) < 1e-9:
        ctx.echo("Zero offset — nothing created.")
        return
    made = []
    for o in objs:
        made.append(ctx.scene.add_from(g.offset_surface(o.shape, dist),
                                       o))
    ctx.echo(f"Offset {len(made)} surface(s).")


@command("shell")
def cmd_shell(ctx):
    objs = yield SelectReq("Select solids to shell", kinds=("solid",))
    from . import dragging
    from .base import PointReq
    # measured off the wall being thickened, so a 1 mm wall is a 1 mm drag
    side = tuple(ctx.cplane.xdir)
    base = dragging.edge_point(objs, side)
    read = dragging.distance_from(base)

    def _shell_to(p):
        t = read(p)
        if t < 1e-9:
            return None
        try:
            return g.make_compound([g.shell_solid(o.shape, t) for o in objs])
        except g.GeometryError:
            return None

    tp = yield PointReq("Wall thickness (click, or type a number)",
                        number_from=(base, side), rubber_from=base,
                        preview_fn=_shell_to)
    thickness = read(tp)
    if thickness < 1e-9:
        ctx.echo("Zero thickness — nothing shelled.")
        return
    for o in objs:
        ctx.scene.replace_shape(o.id, g.shell_solid(o.shape, thickness))
    ctx.echo(f"Shelled {len(objs)} solid(s) with wall {thickness:g}.")


def _profile_and_rails(objs):
    """Of three curves, the profile is the one whose ends touch the other
    two — the rails run side by side and meet nothing. Picked in order
    (rail, rail, profile) when none does."""
    import math
    ends = []
    for o in objs:
        try:
            ends.append(g.curve_endpoints(o.shape))
        except g.GeometryError:
            ends.append(None)
    (lo, hi) = g.bbox(g.make_compound([o.shape for o in objs]))
    near = max(math.dist(lo, hi), 1.0) * 0.02
    for i, o in enumerate(objs):
        if ends[i] is None:
            continue
        others = [e for j, e in enumerate(ends) if j != i and e is not None]
        touches = [any(min(math.dist(p, q) for q in e) < near for e in others)
                   for p in ends[i]]
        if len(others) == 2 and all(touches):
            rails = [x for j, x in enumerate(objs) if j != i]
            return o, rails
    return objs[2], [objs[0], objs[1]]


@command("sweep2")
def cmd_sweep2(ctx):
    """Sweep a profile along two rails. Pick the rails then the profile —
    or hold two surface edges and a curve between them first, and it
    works out which is which."""
    picked = yield SelectReq("Select two rails and a profile (edges of "
                             "surfaces count)", kinds=("curve",),
                             edges_as_curves=True, min_count=3, max_count=3)
    profile, rails = _profile_and_rails(picked)
    rail1, rail2, profiles = [rails[0]], [rails[1]], [profile]
    srf = g.sweep2(profiles[0].shape, rail1[0].shape, rail2[0].shape)
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name}.")

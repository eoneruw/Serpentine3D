"""Second surface/curve wave: patch, blends, projection, helix, text,
unroll."""

from ..core import geometry as g
from .base import (
    NumberReq, OptionReq, PointReq, Scrub, SelectReq, TextReq,
    command,
)


@command("patch", aliases=("networksrf",))
def cmd_patch(ctx):
    curves = yield SelectReq("Select boundary curves", kinds=("curve",),
                             min_count=2)
    srf = g.patch_surface([c.shape for c in curves])
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name} through {len(curves)} boundary curves.")


@command("blendcrv", aliases=("blend",))
def cmd_blendcrv(ctx):
    a = yield SelectReq("Select first curve", kinds=("curve",), max_count=1)
    b = yield SelectReq("Select second curve", kinds=("curve",),
                        max_count=1, allow_preselected=False)
    cont = yield OptionReq("Continuity", options=["Tangent", "Position"],
                           default="Tangent")
    blend = g.blend_curves(a[0].shape, b[0].shape,
                           continuity=cont.lower())
    obj = ctx.scene.add(blend)
    ctx.echo(f"Created blend {obj.name} ({cont.lower()}).")


@command("project")
def cmd_project(ctx):
    curves = yield SelectReq("Select curves to project", kinds=("curve",))
    targets = yield SelectReq("Select target surface",
                              kinds=("surface", "solid"), max_count=1,
                              allow_preselected=False)
    direction = tuple(-c for c in ctx.cplane.normal)
    n = 0
    for c in curves:
        try:
            for piece in g.project_curve(c.shape, targets[0].shape,
                                         direction):
                ctx.scene.add(piece, layer_id=c.layer_id)
                n += 1
        except g.GeometryError as exc:
            ctx.echo(f"{c.name}: {exc}")
    ctx.echo(f"Projected {n} curve(s) onto {targets[0].name}.")


@command("pull")
def cmd_pull(ctx):
    curves = yield SelectReq("Select curves to pull", kinds=("curve",))
    targets = yield SelectReq("Select target surface",
                              kinds=("surface", "solid"), max_count=1,
                              allow_preselected=False)
    n = 0
    for c in curves:
        try:
            for piece in g.pull_curve(c.shape, targets[0].shape):
                ctx.scene.add(piece, layer_id=c.layer_id)
                n += 1
        except g.GeometryError as exc:
            ctx.echo(f"{c.name}: {exc}")
    ctx.echo(f"Pulled {n} curve(s) onto {targets[0].name}.")


@command("helix")
def cmd_helix(ctx):
    import math
    DEFAULT_TURNS = 5.0
    center = yield PointReq("Center of helix base")
    cp = ctx.cplane
    # it winds up out of the plane you drew the base circle on
    up = tuple(float(a) for a in cp.normal)
    w0 = cp.from_world(center)[2]

    def _base_to(p):
        # a helix needs a pitch as well, so the first drag shows the circle
        # it will wind around
        r = math.dist(center, p)
        return g.make_circle(center, r, up) if r > 1e-9 else None

    rp = yield PointReq("Radius (click, or type a number)",
                        number_from=(center, tuple(cp.xdir)),
                        rubber_from=center, preview_fn=_base_to)
    radius = math.dist(center, rp)
    if radius < 1e-9:
        ctx.echo("Zero radius — no helix created.")
        return

    def _helix(pitch, turns):
        if pitch < 1e-9 or turns < 0.01:
            return None
        try:
            return g.make_helix(center, radius, pitch, turns, axis=up)
        except g.GeometryError:
            return None

    pp = yield PointReq("Pitch, the rise per turn (click, or type a number)",
                        number_from=(center, up), axis_lock=(center, up),
                        rubber_from=center,
                        preview_fn=lambda p: _helix(
                            abs(cp.from_world(p)[2] - w0), DEFAULT_TURNS))
    pitch = abs(cp.from_world(pp)[2] - w0)
    if pitch < 1e-9:
        ctx.echo("Zero pitch — no helix created.")
        return

    turns = yield NumberReq("Number of turns", default=DEFAULT_TURNS,
                            minimum=0.01,
                            preview_fn=lambda n: _helix(pitch, float(n)))
    shape = _helix(pitch, turns)
    if shape is None:
        ctx.echo("No helix created.")
        return
    obj = ctx.scene.add(shape)
    ctx.echo(f"Created {obj.name} ({turns:g} turns).")


@command("textobject", aliases=("textcurves",))
def cmd_textobject(ctx):
    from ..core.text import text_curves
    from . import dragging
    content = yield TextReq("Text")
    # where before how big: the height is a size in the model, and there is
    # nothing to measure it against until the text has somewhere to sit
    position = yield PointReq("Position (baseline start)")
    up = tuple(ctx.cplane.ydir)
    read = dragging.distance_from(position)

    def _text_to(p):
        h = read(p)
        if h < 1e-6:
            return None
        try:
            return g.make_compound(
                [g.translate(c, position) for c in text_curves(content, h)])
        except (g.GeometryError, ValueError):
            return None

    hp = yield PointReq("Text height (click, or type a number)",
                        number_from=(position, up), rubber_from=position,
                        preview_fn=_text_to)
    height = read(hp)
    if height < 1e-6:
        ctx.echo("Zero height — no text created.")
        return
    curves = text_curves(content, height)
    made = []
    for c in curves:
        made.append(ctx.scene.add(g.translate(c, position)))
    ctx.echo(f"Created {len(made)} text outline curve(s) — extrude or "
             "planarsrf them for solid lettering.")


@command("unrollsrf", aliases=("unroll",))
def cmd_unrollsrf(ctx):
    objs = yield SelectReq("Select surfaces to unroll (planar, cylindrical "
                           "or conical faces)", kinds=("surface", "solid"))
    layer = ctx.scene.layers.find_by_name("Unrolled")
    layer_id = layer.id if layer else ctx.scene.layers.create(
        "Unrolled", (0.55, 0.85, 0.65)).id
    offset_x = 0.0
    total = 0
    for o in objs:
        for face in g.faces_of(o.shape):
            try:
                curves = g.unroll_face(face)
            except g.GeometryError as exc:
                ctx.echo(f"{o.name}: {exc}")
                continue
            import numpy as np
            mins = np.full(3, np.inf)
            maxs = np.full(3, -np.inf)
            for c in curves:
                mn, mx = g.bbox(c)
                mins = np.minimum(mins, mn)
                maxs = np.maximum(maxs, mx)
            shift = (offset_x - mins[0], -mins[1], 0)
            for c in curves:
                ctx.scene.add(g.translate(c, shift), layer_id=layer_id)
                total += 1
            offset_x += (maxs[0] - mins[0]) + max(
                (maxs[0] - mins[0]) * 0.1, 1.0)
    ctx.scene.notify()
    if total:
        ctx.echo(f"Unrolled {total} boundary curve(s) onto layer "
                 "'Unrolled' (laid out along +X from the origin).")


@command("pipe")
def cmd_pipe(ctx):
    rails = yield SelectReq("Select rail curves", kinds=("curve",))

    from . import dragging
    # a pipe radius is measured out from the rail it wraps, not from anywhere
    # else in the scene
    base = dragging.curve_middle(rails[0].shape)
    side = tuple(ctx.cplane.xdir)
    read = dragging.distance_from(base)

    def _preview(p):
        r = read(p)
        if r < 1e-9:
            return None
        try:
            return g.make_compound(
                [g.pipe(o.shape, r, cap=False) for o in rails])
        except g.GeometryError:
            return None

    rp = yield PointReq("Pipe radius (click, or type a number)",
                        number_from=(base, side), rubber_from=base,
                        choices={"Cap": ["Yes", "No"]}, preview_fn=_preview)
    radius = read(rp)
    if radius < 1e-9:
        ctx.echo("Zero radius — no pipe created.")
        return
    cap = ctx.opt("Cap", "Yes") == "Yes"
    made = []
    for o in rails:
        try:
            made.append(ctx.scene.add(g.pipe(o.shape, radius, cap=cap),
                                      layer_id=o.layer_id))
        except g.GeometryError as exc:
            ctx.echo(f"{o.name}: {exc}")
    ctx.echo(f"Piped {len(made)} curve(s).")


@command("edgesrf", aliases=("srfedges",))
def cmd_edgesrf(ctx):
    curves = yield SelectReq("Select 2, 3 or 4 connected curves",
                             kinds=("curve",), min_count=2, max_count=4)
    srf = g.edge_surface([c.shape for c in curves])
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name} from {len(curves)} edge curves.")


@command("dupborder")
def cmd_dupborder(ctx):
    objs = yield SelectReq("Select surfaces or polysurfaces",
                           kinds=("surface", "solid"))
    made = []
    for o in objs:
        for w in g.free_boundaries(o.shape):
            made.append(ctx.scene.add(w, layer_id=o.layer_id))
    if made:
        ctx.echo(f"Duplicated {len(made)} border curve(s).")
    else:
        ctx.echo("No naked borders found (solids have none).")


@command("dupedge")
def cmd_dupedge(ctx):
    """Duplicate Ctrl+Shift-picked edges as curves."""
    from .solids_edit import _subobject_edge_map
    picked = _subobject_edge_map(ctx)
    if not picked:
        ctx.echo("Ctrl+Shift-click edges first, then run DupEdge.")
        yield from ()
        return
    made = []
    for obj_id, edges in picked.items():
        obj = ctx.scene.get(obj_id)
        for e in edges:
            made.append(ctx.scene.add(g.copy_shape(e),
                                      layer_id=obj.layer_id))
    ctx.echo(f"Duplicated {len(made)} edge(s) as curves.")
    yield from ()


@command("untrim")
def cmd_untrim(ctx):
    objs = yield SelectReq(
        "Select trimmed surfaces",
        kinds=("surface",),
        choices={"Mode": ["Holes", "All"]})
    holes_only = ctx.opt("Mode", "Holes") == "Holes"
    n = 0
    for o in objs:
        try:
            ctx.scene.replace_shape(o.id,
                                    g.untrim(o.shape, holes_only=holes_only))
            n += 1
        except g.GeometryError as exc:
            ctx.echo(f"{o.name}: {exc}")
    ctx.echo(f"Untrimmed {n} surface(s)"
             + (" (holes removed)." if holes_only else " (all trims)."))


@command("extractisocurve", aliases=("isocurve",))
def cmd_extractisocurve(ctx):
    srfs = yield SelectReq("Select surface", kinds=("surface",), max_count=1)
    o = srfs[0]
    made = 0
    while True:
        p = yield PointReq("Point on surface (Enter to finish)",
                           allow_empty=True,
                           choices={"Direction": ["U", "V", "Both"]})
        if p is None:
            break
        d = ctx.opt("Direction", "U").lower()
        for along in (("u", "v") if d == "both" else (d,)):
            try:
                ctx.scene.add(g.iso_curve(o.shape, p, along),
                              layer_id=o.layer_id)
                made += 1
            except g.GeometryError as exc:
                ctx.echo(str(exc))
    ctx.echo(f"Extracted {made} isocurve(s).")


@command("dupfaceborder")
def cmd_dupfaceborder(ctx):
    """Duplicate the border wires of Ctrl+Shift-picked faces as curves."""
    from ..core import occ
    from OCP.TopExp import TopExp_Explorer
    picked = []
    for (obj_id, kind, idx) in ctx.selection.subobjects:
        if kind != "face":
            continue
        obj = ctx.scene.get(obj_id)
        if obj is None:
            continue
        faces = g.faces_of(obj.shape)
        if 0 <= idx < len(faces):
            picked.append((obj, faces[idx]))
    if not picked:
        ctx.echo("Ctrl+Shift-click faces first, then run DupFaceBorder.")
        yield from ()
        return
    made = 0
    for obj, face in picked:
        exp = TopExp_Explorer(face, occ.WIRE)
        while exp.More():
            ctx.scene.add(g.copy_shape(exp.Current()),
                          layer_id=obj.layer_id)
            made += 1
            exp.Next()
    ctx.echo(f"Duplicated {made} border wire(s) as curves.")
    yield from ()


@command("extractsrf", aliases=("extractsurface", "extractface"))
def cmd_extractsrf(ctx):
    """Pull Ctrl+Shift-picked faces out of the polysurfaces holding them.

    Copy=No is Rhino's default and ours: the usual reason to reach for
    this is to rebuild a face, and leaving the original in place would
    put a duplicate surface exactly where the new one has to go.
    """
    picked: dict = {}
    for (obj_id, kind, idx) in ctx.selection.subobjects:
        if kind != "face":
            continue
        obj = ctx.scene.get(obj_id)
        if obj is None or not (0 <= idx < len(g.faces_of(obj.shape))):
            continue
        picked.setdefault(obj_id, []).append(idx)
    if not picked:
        ctx.echo("Ctrl+Shift-click one or more faces first, "
                 "then run ExtractSrf.")
        yield from ()
        return
    copy = yield OptionReq("Copy the faces", options=["No", "Yes"],
                           default="No")
    made = []
    for obj_id, indices in picked.items():
        obj = ctx.scene.get(obj_id)
        faces = g.faces_of(obj.shape)
        for i in sorted(set(indices)):
            made.append(ctx.scene.add_from(g.copy_shape(faces[i]), obj))
        if copy == "Yes":
            continue
        rest = g.remove_faces(obj.shape, indices)
        if rest is None:
            ctx.scene.remove(obj_id)     # every face taken, nothing behind
        else:
            ctx.scene.replace_shape(obj_id, rest)
    # what you extracted is what you want to work on next
    ctx.select_result(made)
    ctx.echo(f"Extracted {len(made)} surface(s)"
             + (" as copies." if copy == "Yes" else "."))


def _picked_face_edges(ctx, why: list | None = None):
    """[(obj, face_shape, edge_shape, edge_index)] from Ctrl+Shift picks.

    A pick that cannot be used is dropped, and if `why` is given a line
    saying what was wrong with it goes there — an edge of a mesh, a
    face where an edge was wanted — so the command can say why it saw
    fewer edges than were picked.
    """
    out = []
    for (obj_id, kind, idx) in ctx.selection.subobjects:
        obj = ctx.scene.get(obj_id)
        if obj is None:
            continue
        if kind != "edge":
            if why is not None:
                why.append(f"{obj.name}: a {kind} is picked, not an edge")
            continue
        if obj.kind in ("mesh", "pointcloud", "picture"):
            if why is not None:
                why.append(f"{obj.name} is a {obj.kind}, not a surface"
                           + (" — MeshToBrep it first"
                              if obj.kind == "mesh" else ""))
            continue
        edges = g.edges_of(obj.shape)
        faces = g.faces_of(obj.shape)
        if not (0 <= idx < len(edges)) or not faces:
            if why is not None:
                why.append(f"{obj.name}: edge {idx} is not one of its "
                           f"{len(edges)} edges" if faces else
                           f"{obj.name} has no faces to blend from")
            continue
        edge = edges[idx]
        support = next(
            (f for f in faces
             if any(e.IsSame(edge) for e in g.edges_of(f))), faces[0])
        out.append((obj, support, edge, idx))
    return out


@command("extendsrf")
def cmd_extendsrf(ctx):
    """Extend a surface past a Ctrl+Shift-picked boundary edge."""
    picked = _picked_face_edges(ctx)
    if not picked:
        ctx.echo("Ctrl+Shift-click a surface boundary edge first, "
                 "then run ExtendSrf.")
        yield from ()
        return
    obj, _, _, idx = picked[0]

    from . import dragging

    def _extend(d):
        return g.extend_surface(obj.shape, idx, d)

    # only the picked edge knows which way the surface grows, and it cannot
    # say — so extend it a hair and watch which way it went
    side = tuple(ctx.cplane.xdir)
    direction = dragging.grow_direction(obj.shape, _extend, fallback=side)
    base = dragging.edge_point([obj], direction)
    read = dragging.distance_from(base)

    def _preview(p):
        d = read(p)
        if d < 1e-9:
            return None
        try:
            return _extend(d)
        except g.GeometryError:
            return None

    lp = yield PointReq("Extension length (click, or type a number)",
                        axis_lock=(base, direction),
                        number_from=(base, direction),
                        rubber_from=base, preview_fn=_preview)
    length = read(lp)
    if length < 1e-9:
        ctx.echo("Zero length — nothing extended.")
        return
    ctx.scene.replace_shape(obj.id, g.extend_surface(obj.shape, idx, length))
    ctx.echo(f"Extended {obj.name} by {length:g}.")


@command("blendsrf")
def cmd_blendsrf(ctx):
    """Blend surface across the gap between two surface edges.

    Ctrl+Shift-click an edge on each surface first, or run it and pick
    them at the prompt. The blend leaves each surface tangent to it
    and appears at once; then Bulge says how far the sections reach
    before turning for the far edge (1 is the even S-curve, type a
    number to see another), Continuity Position drops the tangency
    for a surface that only meets the edges, and Enter keeps what is
    on screen.
    """
    why: list = []
    picked = _picked_face_edges(ctx, why)
    for line in why:
        ctx.echo(line)
    if len(picked) != 2:
        yield SelectReq("Ctrl+Shift-click one edge on each of the two "
                        "surfaces, then Enter",
                        min_count=0, allow_preselected=False)
        why = []
        picked = _picked_face_edges(ctx, why)
        for line in why:
            ctx.echo(line)
    if len(picked) != 2:
        held = len(ctx.selection.subobjects)
        ctx.echo(f"BlendSrf needs one edge picked on each of two surfaces "
                 f"— {len(picked)} usable of {held} picked. Nothing made.")
        return
    (oa, fa, ea, _), (ob, fb, eb, _) = picked
    bulge = 1.0
    continuity = "Tangent"

    def build(b, cont, sections=g.BLEND_SECTIONS):
        return g.blend_between_edges(
            fa, ea, fb, eb, bulge=b,
            continuity="G0" if cont == "Position" else "G1",
            sections=int(sections))

    try:
        shape = build(bulge, continuity)
        how = ""
    except g.GeometryError:
        # the sections would not loft: the filling-based fallbacks, which
        # take no bulge but still put a surface across the gap
        shape, how = g.blend_surfaces_somehow(fa, ea, fb, eb)
        if how == "G1":
            how = ""
    obj = ctx.scene.add_from(shape, oa)
    ctx.select_result([obj])
    if how:
        ctx.echo(f"Created blend {obj.name} between {oa.name} and "
                 f"{ob.name} — {how}.")
        return

    try:
        yield from _shape_the_blend(ctx, obj, build, bulge, continuity)
    except GeneratorExit:
        # Escape: the blend goes with the command, the way Rhino's does
        ctx.scene.remove(obj.id)
        raise


def _shape_the_blend(ctx, obj, build, bulge, continuity):
    """The bulge prompt: drag the chip, click the other, Enter keeps.

    Bulge is a chip you drag sideways and the blend follows as you go;
    Continuity is a chip a click flips between Tangent and Position.
    A typed number is a bulge too, and Bulge=2 the long way round.
    """
    state = {"bulge": bulge, "continuity": continuity,
             "sections": g.BLEND_SECTIONS}

    def rebuild(name, value):
        want = dict(state)
        if name == "Bulge":
            want["bulge"] = float(value)
        elif name == "Sections":
            want["sections"] = int(float(value))
        else:
            want["continuity"] = value
        # raises GeometryError for set_option to report; the last good
        # blend stays on screen and the state stays with it
        shape = build(want["bulge"], want["continuity"], want["sections"])
        state.update(want)
        ctx.scene.replace_shape(obj.id, shape)

    def ghost(v):
        if isinstance(v, (int, float)) and v > 0:
            try:
                return build(float(v), state["continuity"],
                             state["sections"])
            except g.GeometryError:
                return None
        return None

    while True:
        p = yield PointReq("Blend: drag Bulge or Sections, click "
                           "Continuity, Enter to keep it",
                           allow_empty=True, allow_number=True,
                           choices={"Bulge": Scrub(state["bulge"], 0.05,
                                                   5.0, step=0.01),
                                    "Continuity": ["Tangent", "Position"],
                                    "Sections": Scrub(state["sections"],
                                                      3, 60, step=0.1,
                                                      integer=True)},
                           on_option=rebuild, preview_fn=ghost)
        if p is None or isinstance(p, (tuple, list)):
            break
        if isinstance(p, (int, float)):
            if p <= 0:
                ctx.echo("Bulge must be positive.")
                continue
            try:
                rebuild("Bulge", p)
            except g.GeometryError as exc:
                ctx.echo(f"Bulge {p:g}: {exc}")
    ctx.echo(f"Created blend {obj.name} (bulge {state['bulge']:g}, "
             f"{state['continuity'].lower()}, {state['sections']} "
             "sections).")


@command("mergesrf", aliases=("mergesurfaces",))
def cmd_mergesrf(ctx):
    """Two surfaces that share an edge become one, with one net of
    control points.

    Rhino's MergeSrf. Pick two untrimmed surfaces with an edge in common
    — a panel and the blend against it, a surface and an extension sewn
    on in an older build — or one two-face polysurface. Where the two are
    really one surface cut in two they go back together exactly; where
    their edges run alike in space but not in parameter, one surface is
    fitted through both and how far it strays is reported. Smooth=No
    keeps a crease at the seam.
    """
    objs = yield SelectReq("Select two surfaces that share an edge (or a "
                           "two-face polysurface)", min_count=1,
                           max_count=2, kinds=("surface",))
    faces = []
    for o in objs:
        for f in g.faces_of(o.shape):
            faces.append((o, f))
    if len(faces) != 2:
        ctx.echo(f"MergeSrf needs exactly two surfaces — {len(faces)} "
                 "picked. Nothing merged.")
        return
    smooth = yield OptionReq("Smooth across the seam", options=["Yes", "No"],
                             default="Yes")
    (oa, fa), (ob, fb) = faces
    try:
        face, exact, dev = g.merge_surfaces(fa, fb, smooth=(smooth == "Yes"))
    except g.GeometryError as exc:
        ctx.echo(f"MergeSrf: {exc}")
        return
    if ob.id != oa.id:
        ctx.scene.remove(ob.id)
    new = ctx.scene.replace_shape(oa.id, face)
    ctx.select_result([new.id])
    grid = g.surface_control_points(face)[1]
    how = ("exactly" if exact
           else f"fitted, within {dev:.3g} {ctx.scene.units}")
    ctx.echo(f"Merged into one surface ({how}), {grid[0]}×{grid[1]} "
             "control points.")

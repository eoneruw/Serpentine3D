"""In-app command reference."""

from .base import TextReq, all_commands, command, resolve

# module name -> section heading in the reference
_SECTIONS = {
    "curves": "Curves", "surfaces": "Surfaces", "surfaces2": "Surfaces",
    "solids": "Solids", "solids_edit": "Solid editing",
    "boolean": "Booleans", "transform": "Transforms",
    "edit": "Editing", "deform_cmds": "Deformation",
    "select": "Selection", "organize": "Organisation",
    "view": "Display & views", "camera_cmds": "Camera",
    "drafting": "Drafting & layouts", "file": "Files",
    "help_cmd": "Help",
}


def _doc_of(cd) -> str:
    """The first sentence of a command's docstring — whole, however the
    lines were wrapped — or its label when it has none. The first line
    alone cut "Rotate around an axis picked as two points: type an" off
    mid-thought in the help and the command table."""
    import re
    doc = (cd.fn.__doc__ or "").strip()
    if not doc:
        return cd.label
    first = doc.split("\n\n", 1)[0]
    text = " ".join(line.strip() for line in first.splitlines())
    m = re.search(r"[.!?](?=\s|$)", text)
    return text[:m.end()] if m else text


def _section_of(cd) -> str:
    mod = cd.fn.__module__.rsplit(".", 1)[-1]
    return _SECTIONS.get(mod, mod.capitalize())


def command_reference() -> dict[str, list]:
    """{section: [(name, aliases, doc), ...]} for UI help browsers."""
    out: dict[str, list] = {}
    for cd in all_commands():
        out.setdefault(_section_of(cd), []).append(
            (cd.name, cd.aliases, _doc_of(cd)))
    return {k: out[k] for k in sorted(out)}


@command("help", aliases=("?",), mutates=False)
def cmd_help(ctx):
    """Describe a command, or list every command by category."""
    name = yield TextReq("Command name (Enter lists everything)", default="")
    name = (name or "").strip()
    if name:
        cd = resolve(name)
        if cd is None:
            ctx.echo(f"No command named '{name}'. "
                     "Run 'help' with no name for the full list.")
            return
        alias = f" (aliases: {', '.join(cd.aliases)})" if cd.aliases else ""
        ctx.echo(f"{cd.name}{alias} — {_doc_of(cd)}")
        return
    for section, cmds in command_reference().items():
        ctx.echo(f"{section}: " + ", ".join(n for n, _, _ in cmds))
    ctx.echo("Type 'help <command>' for details; Tab completes names; "
             "F1 opens the browsable reference.")

"""A command's one-line description is its first sentence, whole.

The help and the generated command table took the first line of the
docstring, which for a wrapped sentence was half of it: "Rotate around
an arbitrary axis picked as two points: type an". The first sentence,
however it was wrapped, is what a line is for.
"""

from serpentine3d.commands import help_cmd
from serpentine3d.commands.base import resolve


def _doc(name):
    return help_cmd._doc_of(resolve(name))


def test_a_wrapped_first_sentence_comes_whole():
    text = _doc("rotate3d")
    assert not text.endswith("an")
    assert text.endswith((".", "!", "?"))


def test_only_the_first_sentence():
    text = _doc("help")
    assert text.count(". ") == 0 and text.endswith(".")


def test_a_command_without_a_docstring_keeps_its_label():
    class _Fake:
        fn = type("F", (), {"__doc__": None})
        label = "Nothing"
    assert help_cmd._doc_of(_Fake) == "Nothing"


def test_every_command_gets_a_sentence():
    for _section, cmds in help_cmd.command_reference().items():
        for name, _aliases, doc in cmds:
            assert doc and not doc.endswith((",", ":", "—", "-")), (name, doc)

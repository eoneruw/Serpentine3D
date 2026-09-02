"""In-app AI assistant: SSE client, tool dispatch, agent loop."""

import json

import httpx
import pytest

from serpentine3d.ai import tools as T
from serpentine3d.ai.client import AiError, AnthropicClient, AuthError
from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Never let these tests read or write the user's real config."""
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("SERP3D_NO_RPC", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _sse(events) -> bytes:
    out = []
    for name, data in events:
        out.append(f"event: {name}\ndata: {json.dumps(data)}\n\n")
    return "".join(out).encode()


_TEXT_STREAM = [
    ("message_start", {"message": {"usage": {"input_tokens": 10}}}),
    ("content_block_start", {"index": 0,
                             "content_block": {"type": "text", "text": ""}}),
    ("content_block_delta", {"index": 0,
                             "delta": {"type": "text_delta",
                                       "text": "Hello "}}),
    ("content_block_delta", {"index": 0,
                             "delta": {"type": "text_delta",
                                       "text": "world"}}),
    ("content_block_stop", {"index": 0}),
    ("message_delta", {"delta": {"stop_reason": "end_turn"},
                       "usage": {"output_tokens": 5}}),
    ("message_stop", {}),
]

_TOOL_STREAM = [
    ("content_block_start", {"index": 0, "content_block": {
        "type": "tool_use", "id": "tu_1", "name": "run_command",
        "input": {}}}),
    ("content_block_delta", {"index": 0, "delta": {
        "type": "input_json_delta",
        "partial_json": '{"command": "box", "inputs": '}}),
    ("content_block_delta", {"index": 0, "delta": {
        "type": "input_json_delta",
        "partial_json": '["0,0,0", "10", "10", "3"]}'}}),
    ("content_block_stop", {"index": 0}),
    ("message_delta", {"delta": {"stop_reason": "tool_use"}, "usage": {}}),
]


def _client(stream_bytes, status=200):
    def handler(request):
        return httpx.Response(
            status, content=stream_bytes,
            headers={"content-type": "text/event-stream"})
    return AnthropicClient("sk-test", transport=httpx.MockTransport(handler))


def test_client_streams_text_and_usage():
    client = _client(_sse(_TEXT_STREAM))
    got = []
    reply = client.stream_message("sys", [{"role": "user", "content": "hi"}],
                                  tools=[], on_text=got.append)
    assert "".join(got) == "Hello world"
    assert reply["content"] == [{"type": "text", "text": "Hello world"}]
    assert reply["stop_reason"] == "end_turn"
    assert reply["usage"]["output_tokens"] == 5


def test_client_accumulates_tool_input_json():
    client = _client(_sse(_TOOL_STREAM))
    reply = client.stream_message("sys", [], tools=[])
    block = reply["content"][0]
    assert block["type"] == "tool_use"
    assert block["input"] == {"command": "box",
                              "inputs": ["0,0,0", "10", "10", "3"]}
    assert reply["stop_reason"] == "tool_use"


_THINKING_STREAM = [
    ("content_block_start", {"index": 0, "content_block": {
        "type": "thinking", "thinking": ""}}),
    ("content_block_delta", {"index": 0, "delta": {
        "type": "thinking_delta", "thinking": "Box first, "}}),
    ("content_block_delta", {"index": 0, "delta": {
        "type": "thinking_delta", "thinking": "then fillet."}}),
    ("content_block_delta", {"index": 0, "delta": {
        "type": "signature_delta", "signature": "sig_abc"}}),
    ("content_block_stop", {"index": 0}),
    ("content_block_start", {"index": 1,
                             "content_block": {"type": "text", "text": ""}}),
    ("content_block_delta", {"index": 1,
                             "delta": {"type": "text_delta", "text": "Done."}}),
    ("content_block_stop", {"index": 1}),
    ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {}}),
]


def test_client_keeps_a_thinking_block_whole():
    """Seen live: the model thought before answering, the stream kept only
    the empty start of the thinking block, and the next turn sent it back as
    history — 'API error 400: each thinking block must contain thinking'.
    The block is kept with its text and signature so it can be echoed."""
    client = _client(_sse(_THINKING_STREAM))
    got = []
    reply = client.stream_message("sys", [], tools=[], on_text=got.append)
    assert "".join(got) == "Done.", "thinking is never shown as text"
    assert reply["content"] == [
        {"type": "thinking", "thinking": "Box first, then fillet.",
         "signature": "sig_abc"},
        {"type": "text", "text": "Done."},
    ]


def test_client_drops_an_unfinished_thinking_block():
    """A thinking block with no signature cannot be echoed; better to lose
    the thought than to poison every later turn of the conversation."""
    cut = [e for e in _THINKING_STREAM
           if e[1].get("delta", {}).get("type") != "signature_delta"]
    client = _client(_sse(cut))
    reply = client.stream_message("sys", [], tools=[])
    assert reply["content"] == [{"type": "text", "text": "Done."}]


def test_client_auth_error():
    client = _client(b'{"error": {"message": "bad key"}}', status=401)
    with pytest.raises(AuthError):
        client.stream_message("sys", [], tools=[])


def test_client_friendly_overload_error():
    client = _client(b'{"error": {"message": "overloaded"}}', status=529)
    with pytest.raises(AiError, match="overloaded"):
        client.stream_message("sys", [], tools=[])


# ---------------------------------------------------------------- dispatch


def _api():
    _qapp()
    from serpentine3d.api import SerpApi
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    return SerpApi(w), w


def test_dispatch_run_command_and_scene_info():
    api, w = _api()
    out = T.dispatch(api, "run_command",
                     {"command": "box", "inputs": ["0,0,0", "10,10,0", "3"]})
    assert isinstance(out, str)
    info = json.loads(T.dispatch(api, "scene_info", {}))
    assert info["object_count"] == 1
    assert info["objects"][0]["kind"] == "solid"


def _require_gl(w):
    if w.viewport.grabFramebuffer().isNull():
        pytest.skip("no GL framebuffer on this platform (CI offscreen)")


def test_dispatch_screenshot_returns_image():
    api, w = _api()
    w.scene.add(g.make_box((0, 0, 0), 5, 5, 5))
    _require_gl(w)
    result = T.dispatch(api, "screenshot", {"width": 320})
    assert isinstance(result, T.ImageResult)
    assert result.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_dispatch_unknown_tool():
    from serpentine3d.api import ApiError
    api, _ = _api()
    with pytest.raises(ApiError):
        T.dispatch(api, "nope", {})


def test_system_prompt_lists_commands():
    from serpentine3d.ai.agent import build_system_prompt
    text = build_system_prompt()
    assert "filletedge" in text
    assert "zoomextents" in text
    assert "Z is up" in text


# ------------------------------------------------------------------- agent


class ScriptedClient:
    """Plays back canned replies; records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def stream_message(self, system, messages, tools, max_tokens=8192,
                       on_text=None, should_stop=None, on_thinking=None):
        self.sent.append([dict(m) for m in messages])
        reply = self.replies.pop(0)
        for block in reply["content"]:
            if block["type"] == "thinking" and on_thinking:
                on_thinking(block["thinking"])
            if block["type"] == "text" and on_text:
                on_text(block["text"])
        return reply


def _tool_use(name, args, call_id="tu_1"):
    return {"content": [{"type": "tool_use", "id": call_id, "name": name,
                         "input": args}],
            "stop_reason": "tool_use", "usage": {}}


def _text(text):
    return {"content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn", "usage": {"output_tokens": 3}}


def _run_agent(agent, prompt, timeout_ms=30000):
    """Drive one turn to completion inside the Qt event loop."""
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    loop = QEventLoop()
    outcome = {}
    agent.turnFinished.connect(
        lambda r: (outcome.__setitem__("stop", r), loop.quit()))
    agent.errorRaised.connect(
        lambda e: (outcome.__setitem__("error", e), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    agent.send(prompt)
    loop.exec()
    QCoreApplication.processEvents()
    return outcome


def test_agent_executes_tools_then_answers():
    from serpentine3d.ai.agent import Agent
    api, w = _api()
    client = ScriptedClient([
        _tool_use("run_command",
                  {"command": "box", "inputs": ["0,0,0", "4,4,0", "4"]}),
        _text("Built you a box."),
    ])
    agent = Agent(api, client, parent=w)
    chips = []
    agent.toolStarted.connect(lambda n, s: chips.append(s))
    outcome = _run_agent(agent, "make a box")
    assert outcome.get("stop") == "end_turn"
    assert w.scene.all()[0].kind == "solid"
    assert chips and "box" in chips[0]
    # transcript alternates correctly: user, assistant(tool), user(result),
    # assistant(text)
    roles = [m["role"] for m in agent.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    result_block = agent.messages[2]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "tu_1"


def test_agent_tool_error_feeds_back_not_raises():
    from serpentine3d.ai.agent import Agent
    api, w = _api()
    client = ScriptedClient([
        _tool_use("boolean", {"operation": "union",
                              "targets": ["Ghost"], "tools": ["Ghost2"]}),
        _text("That object does not exist."),
    ])
    agent = Agent(api, client, parent=w)
    outcome = _run_agent(agent, "union the ghosts")
    assert outcome.get("stop") == "end_turn"
    err_block = agent.messages[2]["content"][0]
    assert err_block["is_error"] is True


def test_agent_screenshot_result_is_image_block():
    from serpentine3d.ai.agent import Agent
    api, w = _api()
    w.scene.add(g.make_box((0, 0, 0), 5, 5, 5))
    _require_gl(w)
    client = ScriptedClient([
        _tool_use("screenshot", {"width": 320}),
        _text("Looks right."),
    ])
    agent = Agent(api, client, parent=w)
    outcome = _run_agent(agent, "check your work")
    assert outcome.get("stop") == "end_turn"
    content = agent.messages[2]["content"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"


def test_agent_api_error_cleans_transcript():
    from serpentine3d.ai.agent import Agent
    api, w = _api()

    class DyingClient:
        def stream_message(self, *a, **k):
            raise AiError("boom")

    agent = Agent(api, DyingClient(), parent=w)
    outcome = _run_agent(agent, "hello")
    assert "boom" in outcome.get("error", "")
    # the user message stays; a retry can resend it
    assert [m["role"] for m in agent.messages] == ["user"]


def test_agent_step_limit():
    from serpentine3d.ai.agent import Agent
    api, w = _api()
    client = ScriptedClient(
        [_tool_use("scene_info", {}, f"tu_{i}") for i in range(99)])
    agent = Agent(api, client, max_steps=3, parent=w)
    outcome = _run_agent(agent, "loop forever")
    assert outcome.get("stop") == "step limit reached"


def test_panel_opens_and_runs_scripted_turn(tmp_path, monkeypatch):
    _qapp()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    panel = w.show_ai_panel()
    # no key -> setup card is shown, input hidden
    assert panel.setup_card.isVisibleTo(panel)
    assert not panel.input_row.isVisibleTo(panel)
    # saving a key swaps to the input row
    panel.key_edit.setText("sk-test")
    panel._save_key()
    assert w.cfg.get("ai", "api_key") == "sk-test"
    assert panel.input_row.isVisibleTo(panel)
    # scripted turn drives real geometry through the panel's agent
    panel._ensure_agent()
    panel.agent.client = ScriptedClient([
        _tool_use("run_command",
                  {"command": "sphere", "inputs": ["0,0,0", "6"]}),
        _text("A sphere, as requested."),
    ])
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    panel.agent.turnFinished.connect(lambda r: loop.quit())
    panel.agent.errorRaised.connect(lambda e: loop.quit())
    QTimer.singleShot(30000, loop.quit)
    panel.input.setPlainText("a sphere please")
    panel._send()
    loop.exec()
    assert len(w.scene.all()) == 1
    assert panel.btn_send.text() == "Send"
    assert panel.input.isEnabled()


def test_panel_says_what_it_is_waiting_for(monkeypatch):
    """Seen live: a question sent, and nothing in the panel for a long
    while. The model was thinking, which arrives as deltas the panel
    rightly does not print, and a panel that prints nothing looks hung.
    It says 'Connecting…' the moment Send is pressed, 'Thinking…' once
    the model is heard from, 'Working…' after a tool while the next words
    are awaited, and clears the line whenever there is something real to
    show."""
    _qapp()
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w._saved_revision = w.scene.revision
    panel = w.show_ai_panel()
    panel.key_edit.setText("sk-test")
    panel._save_key()
    panel._ensure_agent()
    # the agent's worker is not the thing under test; hold it still and
    # feed the panel the signals it would have sent, in the order it does
    monkeypatch.setattr(panel.agent, "send", lambda text: None)
    assert panel.status_text() == ""

    panel.input.setPlainText("what is in the scene?")
    panel._send()
    assert panel.status_text() == "Connecting…"

    panel._on_thinking("Box first, ")
    panel._on_thinking("then fillet.")
    assert panel.status_text() == "Thinking…"

    panel._on_tool_start("scene_info", "scene_info")
    assert panel.status_text() == "", "a running tool is its own sign of life"
    panel._on_tool_finish("scene_info", True, "1 object")
    assert panel.status_text() == "Working…"

    panel._on_text("One box.")
    assert panel.status_text() == "", "real words replace the status line"
    panel._on_finished("end_turn")
    assert panel.status_text() == ""
    assert panel.btn_send.text() == "Send"


def test_panel_status_counts_the_seconds(monkeypatch):
    """A number that grows is the difference between 'waiting' and
    'stuck': it says the panel is alive even when the model is not
    saying anything yet."""
    _qapp()
    from serpentine3d.app import MainWindow
    from serpentine3d.ai import panel as panel_mod
    w = MainWindow()
    w._saved_revision = w.scene.revision
    panel = w.show_ai_panel()
    now = [1000.0]
    monkeypatch.setattr(panel_mod.time, "monotonic", lambda: now[0])
    panel._set_status("Thinking…")
    assert panel.status_text() == "Thinking…", "no count for the first moments"
    now[0] += 12
    panel._tick_status()
    assert panel.status_text() == "Thinking…  12 s"
    panel._clear_status()
    assert panel.status_text() == ""
    assert not panel._status_timer.isActive()


def test_ai_command_registered():
    from serpentine3d.commands.base import resolve
    cd = resolve("ai")
    assert cd is not None and not cd.mutates
    assert resolve("assistant").name == "ai"

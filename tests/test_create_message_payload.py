from types import SimpleNamespace

from backend.function_logic import FunctionBackend


def test_create_message_payload_includes_canvas_uuid(monkeypatch):
    captured = {}

    class FakeManager:
        def call(self, name, **kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs
            return {"message_uuid": "message-1"}

    monkeypatch.setattr("backend.function_logic._get_canvas_designer_api_manager", lambda: FakeManager())
    oe = SimpleNamespace(
        channel_id=None,
        access_token="token",
        organization=SimpleNamespace(organization_id="org-1"),
        extra_params={
            "conversation_uuid": "conversation-1",
            "design_context": {"canvas_uuid": "canvas-1"},
            "tool_calls": [
                {
                    "args": {
                        "reasoning": "Reply on canvas.",
                        "content": "Thanks, I added that to the map.",
                    }
                }
            ],
        },
    )

    result = FunctionBackend(oe).process_request()

    assert result == "Canvas reply sent to conversation conversation-1 (message message-1)."
    assert captured["name"] == "create_message"
    assert captured["kwargs"]["conversation_uuid"] == "conversation-1"
    assert captured["kwargs"]["canvas_uuid"] == "canvas-1"
    assert captured["kwargs"]["message"] == "Thanks, I added that to the map."
    assert captured["kwargs"]["sender"] == "assistant"

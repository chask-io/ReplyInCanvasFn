import logging
import os
from typing import Any, Dict, Optional

from chask_foundation.api.api_manager import ApiManager
from chask_foundation.backend.models import OrchestrationEvent

logger = logging.getLogger()
logger.setLevel(logging.INFO)


_canvas_designer_api_manager: Optional[ApiManager] = None


def _get_canvas_designer_api_manager() -> ApiManager:
    global _canvas_designer_api_manager
    if _canvas_designer_api_manager is not None:
        return _canvas_designer_api_manager

    base_domain = os.getenv("BASE_DOMAIN")
    if not base_domain:
        raise ValueError("BASE_DOMAIN is required for chask_api calls")
    if not (base_domain.startswith("http://") or base_domain.startswith("https://")):
        base_domain = f"https://{base_domain}"

    manager = ApiManager(base_url=f"{base_domain.rstrip('/')}/api/v2/channels/canvas-designer")

    @manager.register("create_message", "create-message", "POST")
    def _create_message(
        conversation_uuid: str,
        message: str,
        sender: str,
        canvas_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "conversation_uuid": conversation_uuid,
            "message": message,
            "sender": sender,
        }
        if canvas_uuid:
            payload["canvas_uuid"] = canvas_uuid
        return {"json": payload}

    _canvas_designer_api_manager = manager
    return _canvas_designer_api_manager


class FunctionBackend:
    def __init__(self, orchestration_event: OrchestrationEvent):
        self.orchestration_event = orchestration_event
        logger.info(
            "Initialized ReplyInCanvasFn for org: %s",
            orchestration_event.organization.organization_id,
        )

    def process_request(self) -> str:
        tool_args = self._extract_tool_args()
        is_test = self._is_test_invocation()
        reasoning = self._normalize_text(tool_args.get("reasoning")) or (
            "Test canvas reply." if is_test else ""
        )
        content = self._normalize_text(tool_args.get("content")) or (
            "Test canvas reply content." if is_test else ""
        )
        if not reasoning:
            raise ValueError("Missing required parameter: reasoning")
        if not content:
            raise ValueError("Missing required parameter: content")

        conversation_uuid = self._resolve_conversation_uuid()
        if not conversation_uuid:
            raise ValueError("Missing canvas conversation_uuid in event context")
        canvas_uuid = self._resolve_canvas_uuid()

        if is_test:
            logger.info(
                "Test invocation accepted for canvas conversation=%s canvas=%s content_len=%d",
                conversation_uuid,
                canvas_uuid,
                len(content),
            )
            return f"Test canvas reply accepted for conversation {conversation_uuid}."

        logger.info(
            "Posting canvas reply conversation=%s canvas=%s content_len=%d reasoning=%s",
            conversation_uuid,
            canvas_uuid,
            len(content),
            reasoning[:120],
        )
        response = _get_canvas_designer_api_manager().call(
            "create_message",
            conversation_uuid=conversation_uuid,
            message=content,
            sender="assistant",
            canvas_uuid=canvas_uuid,
            access_token=self.orchestration_event.access_token,
            organization_id=str(self.orchestration_event.organization.organization_id),
            timeout=30,
        )

        message_uuid = response.get("message_uuid") if isinstance(response, dict) else None
        if not message_uuid:
            raise RuntimeError(f"Canvas reply API response missing message_uuid: {response}")

        return f"Canvas reply sent to conversation {conversation_uuid} (message {message_uuid})."

    def _extract_tool_args(self) -> Dict[str, Any]:
        extra_params = self.orchestration_event.extra_params or {}
        tool_calls = extra_params.get("tool_calls") or []
        if not tool_calls:
            logger.warning("No tool calls found in orchestration event")
            return {}
        return tool_calls[0].get("args") or {}

    def _resolve_conversation_uuid(self) -> Optional[str]:
        extra_params = self.orchestration_event.extra_params or {}
        value = (
            extra_params.get("conversation_uuid")
            or self.orchestration_event.channel_id
            or extra_params.get("channel_id")
        )
        return self._normalize_optional_text(value)

    def _resolve_canvas_uuid(self) -> Optional[str]:
        extra_params = self.orchestration_event.extra_params or {}
        design_context = extra_params.get("design_context") or {}
        if not isinstance(design_context, dict):
            return None
        return self._normalize_optional_text(design_context.get("canvas_uuid"))

    def _is_test_invocation(self) -> bool:
        extra_params = self.orchestration_event.extra_params or {}
        return bool(extra_params.get("is_test") or extra_params.get("is_node_test"))

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _normalize_optional_text(self, value: Any) -> Optional[str]:
        text = self._normalize_text(value)
        return text or None

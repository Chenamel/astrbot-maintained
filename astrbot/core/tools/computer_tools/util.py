import enum
from pathlib import Path

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.code_delivery_policy import execution_denial
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    resolve_workspace_root_for_umo,
)


def workspace_root(umo: str) -> Path:
    """Return the legacy workspace root for compatibility.

    Args:
        umo: Unified message origin.

    Returns:
        Legacy per-session workspace root.
    """
    return (
        Path(get_astrbot_workspaces_path()) / normalize_umo_for_workspace(umo)
    ).resolve(strict=False)


async def workspace_root_for_context(
    context: ContextWrapper[AstrAgentContext],
) -> Path:
    """Resolve the workspace root for a tool call context.

    Args:
        context: Tool call context.

    Returns:
        Workspace root used as cwd.
    """
    umo = context.context.event.unified_msg_origin
    db = getattr(context.context.context, "_db", None)
    if not isinstance(db, BaseDatabase):
        return workspace_root(umo)
    try:
        return await resolve_workspace_root_for_umo(umo, db)
    except Exception:
        return workspace_root(umo)


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "none"))
    return runtime == "local"


class ToolPermissionLevel(enum.Enum):
    """Permission check applied by :func:`check_tool_permission`.

    Attributes:
        IDENTITY: Accept administrators only, driven by the
            ``computer_use_require_admin`` provider setting.
        EXECUTION: Re-check whether the current message authorizes an
            execution-style operation.
    """

    #: Admin-only gate reading ``provider_settings.computer_use_require_admin``.
    IDENTITY = "identity"
    #: Current-message authorization gate reading the execution policy.
    EXECUTION = "execution"


def check_tool_permission(
    context: ContextWrapper[AstrAgentContext],
    operation_name: str,
    level: ToolPermissionLevel,
) -> str | None:
    """Gate a computer-use tool behind the single permission entry.

    Both checks live here so that every tool shares one implementation; each
    caller still picks exactly one level, keeping its existing strength.

    Args:
        context: Tool call context.
        operation_name: Operation name reported in the denial message.
        level: Check to apply, see :class:`ToolPermissionLevel`.

    Returns:
        Error string for the caller to return, or None when allowed.
    """
    event = context.context.event
    config = context.context.context.get_config(umo=event.unified_msg_origin)

    if level is ToolPermissionLevel.IDENTITY:
        provider_settings = config.get("provider_settings", {})
        require_admin = provider_settings.get("computer_use_require_admin", True)
        if require_admin and event.role != "admin":
            return (
                f"error: Permission denied. {operation_name} is only allowed for admin users. "
                "Tell user to set admins in `AstrBot WebUI -> Config -> General Config` by adding their user ID to the admins list if they need this feature. "
                f"User's ID is: {event.get_sender_id()}. User's ID can be found by using /sid command."
            )
        return None

    # The policy reads get_sender_id() without checking for it, so an event
    # stand-in without the method would raise instead of being denied. Treat
    # such a context as having no sender, which the policy already rejects.
    policy_event = event if callable(getattr(event, "get_sender_id", None)) else None
    error = execution_denial(policy_event, config)
    logger.info(
        "Execution entry operation=%s message_id=%s allowed=%s",
        operation_name,
        getattr(getattr(event, "message_obj", None), "message_id", ""),
        error is None,
    )
    return error


def check_admin_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    """Run the admin-only check for callers kept at their upstream spelling.

    Upstream modules and the tools package public surface reference this name,
    so it stays as a forwarder without its own decision logic.

    Args:
        context: Tool call context.
        operation_name: Operation name reported in the denial message.

    Returns:
        Error string for the caller to return, or None when allowed.
    """
    return check_tool_permission(context, operation_name, ToolPermissionLevel.IDENTITY)

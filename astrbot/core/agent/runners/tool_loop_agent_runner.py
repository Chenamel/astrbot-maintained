import asyncio
import copy
import json
import re
import sys
import time
import traceback
import typing as T
from contextlib import suppress
from dataclasses import dataclass, field, replace

from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.agent.message import ImageURLPart, TextPart, ThinkPart
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_image_cache import tool_image_cache
from astrbot.core.code_delivery_policy import (
    CODE_DELIVERY_FAILURE,
    SAFETY_REFUSAL_PATTERN,
    code_task_spec,
    has_code_delivery,
)
from astrbot.core.config.agent_runner import normalize_hook_timing_mode
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
    ToolCallsResult,
)
from astrbot.core.provider.modalities import (
    log_context_sanitize_stats,
    sanitize_contexts_by_modalities,
)
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.direct_turns import (
    begin_tool,
    get_tool_result,
    is_current,
    record_tool_result,
    release_tool,
    wait_tool_result,
)

from ..context.compressor import ContextCompressor
from ..context.config import ContextConfig
from ..context.manager import ContextManager
from ..context.token_counter import EstimateTokenCounter, TokenCounter
from ..hooks import BaseAgentRunHooks
from ..message import (
    AssistantMessageSegment,
    Message,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
)
from ..response import AgentResponseData, AgentStats
from ..run_context import ContextWrapper, TContext
from ..tool_executor import BaseFunctionToolExecutor
from .base import AgentResponse, AgentState, BaseAgentRunner
from .tool_loop_support import (
    ToolExecutorResultT,
    _ToolExecutionInterrupted,
    build_repeated_tool_call_guidance,
    iter_tool_executor_results,
    read_tool_hint,
    track_tool_call_streak,
    truncate_tool_result_preview,
    write_tool_result_overflow_file,
)

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

#: Timeout for the auxiliary LLM calls this runner performs: the delivery-repair
#: request and the final generation after a tool-failure limit.
AUXILIARY_LLM_TIMEOUT_SEC = 30


@dataclass(slots=True)
class _HandleFunctionToolsResult:
    kind: T.Literal["message_chain", "tool_call_result_blocks", "cached_image"]
    message_chain: MessageChain | None = None
    tool_call_result_blocks: list[ToolCallMessageSegment] | None = None
    cached_image: T.Any = None

    @classmethod
    def from_message_chain(cls, chain: MessageChain) -> "_HandleFunctionToolsResult":
        return cls(kind="message_chain", message_chain=chain)

    @classmethod
    def from_tool_call_result_blocks(
        cls, blocks: list[ToolCallMessageSegment]
    ) -> "_HandleFunctionToolsResult":
        return cls(kind="tool_call_result_blocks", tool_call_result_blocks=blocks)

    @classmethod
    def from_cached_image(cls, image: T.Any) -> "_HandleFunctionToolsResult":
        return cls(kind="cached_image", cached_image=image)


@dataclass(slots=True)
class FollowUpTicket:
    seq: int
    text: str
    consumed: bool = False
    resolved: asyncio.Event = field(default_factory=asyncio.Event)


AwaitableResultT = T.TypeVar("AwaitableResultT")


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    TOOL_RESULT_MAX_ESTIMATED_TOKENS = 27_500
    TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS = 7000
    EMPTY_OUTPUT_RETRY_ATTEMPTS = 3
    EMPTY_OUTPUT_RETRY_WAIT_MIN_S = 1
    EMPTY_OUTPUT_RETRY_WAIT_MAX_S = 4
    USER_INTERRUPTION_REQUEST = "Stop output."
    USER_INTERRUPTION_MESSAGE = "Output stopped."
    FOLLOW_UP_NOTICE_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] User sent follow-up messages while tool execution "
        "was in progress. Prioritize these follow-up instructions in your next "
        "actions. In your very next action, briefly acknowledge to the user "
        "that their follow-up message(s) were received before continuing.\n"
        "{follow_up_lines}"
    )
    MAX_STEPS_REACHED_PROMPT = (
        "Maximum tool call limit reached. "
        "Stop calling tools, and based on the information you have gathered, "
        "summarize your task and findings, and reply to the user directly."
    )
    SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE = (
        "You have decided to call tool(s): {tool_names}. Now call the tool(s) "
        "with required arguments using the tool schema, and follow the existing "
        "tool-use rules."
    )
    SKILLS_LIKE_REQUERY_REPAIR_INSTRUCTION = (
        "This is the second-stage tool execution step. "
        "You must do exactly one of the following: "
        "1. Call one of the selected tools using the provided tool schema. "
        "2. If calling a tool is no longer possible or appropriate, reply to the user "
        "with a brief explanation of why. "
        "Do not return an empty response. "
        "Do not ignore the selected tools without explanation."
    )
    REPEATED_TOOL_NOTICE_L1_THRESHOLD = 3
    REPEATED_TOOL_NOTICE_L2_THRESHOLD = 4
    REPEATED_TOOL_NOTICE_L3_THRESHOLD = 5
    REPEATED_TOOL_FAILURE_LIMIT = 3
    MALFORMED_TOOL_NAME_PLACEHOLDER = "__malformed_tool_name__"
    REPEATED_TOOL_NOTICE_L1_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] By the way, you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Double-check whether another tool, different arguments, or a summary would "
        "move the task forward better."
    )
    REPEATED_TOOL_NOTICE_L2_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Unless this repetition is clearly necessary, stop repeating the same action "
        "and either switch tools, refine parameters, or summarize what is still "
        "missing."
    )
    REPEATED_TOOL_NOTICE_L3_TEMPLATE = (
        "\n\n[SYSTEM NOTICE] Important: you have executed the same tool "
        "`{tool_name}` with the same arguments {streak} times consecutively. "
        "Repetition is now very high. Continue only if each call is clearly producing "
        "new information. Otherwise, change strategy, adjust arguments, or explain "
        "the limitation to the user."
    )
    TOOL_RESULT_OVERFLOW_NOTICE_TEMPLATE = (
        "Truncated tool output preview shown above. "
        "The tool output was too large to include directly and was written to "
        "`{overflow_path}`. Use {read_tool_hint} to inspect it. "
        "Use a narrower window when reading large files."
    )

    def _get_persona_custom_error_message(self) -> str | None:
        """Read persona-level custom error message from event extras when available."""
        event = getattr(self.run_context.context, "event", None)
        return extract_persona_custom_error_message_from_event(event)

    async def _complete_with_assistant_response(self, llm_resp: LLMResponse) -> None:
        """Finalize the current step as a plain assistant response with no tool calls."""
        event = getattr(self.run_context.context, "event", None)
        task = code_task_spec(event)
        safe_refusal = SAFETY_REFUSAL_PATTERN.search(llm_resp.completion_text or "")
        if (
            task
            and not safe_refusal
            and not getattr(llm_resp, "image_input_unavailable", False)
            and not self._code_repair_attempted
            and not has_code_delivery(llm_resp.completion_text or "", task[1])
        ):
            self._code_repair_attempted = True
            task_text, language = task
            repaired_text = CODE_DELIVERY_FAILURE
            outcome = "incomplete"
            repair_context = list(self.run_context.messages)
            repair_context.append(
                Message(
                    role="assistant",
                    content=llm_resp.completion_text or "[No source delivered]",
                )
            )
            repair_context.append(
                Message(
                    role="user",
                    content=(
                        "[Source delivery correction] The current task requires actual source, "
                        "not a promise or execution results. Do not call tools or repeat any action. "
                        "Return complete usable source in a fenced code block in the requested "
                        f"language ({language or 'as requested'}), preserving the task requirements. "
                        "If the task is unsafe, briefly decline instead.\n"
                        f"Task and current follow-up:\n{task_text}"
                    ),
                )
            )
            try:
                repair = await asyncio.wait_for(
                    self.provider.text_chat(
                        contexts=self._sanitize_contexts_for_provider(repair_context),
                        func_tool=None,
                        model=self.req.model,
                        session_id=self.req.session_id,
                        abort_signal=self._abort_signal,
                        request_max_retries=0,
                    ),
                    timeout=AUXILIARY_LLM_TIMEOUT_SEC,
                )
                if (
                    repair.role == "assistant"
                    and not repair.tools_call_name
                    and has_code_delivery(repair.completion_text or "", language)
                ):
                    repaired_text = repair.completion_text
                    outcome = "completed"
                elif (
                    repair.role == "assistant"
                    and not repair.tools_call_name
                    and SAFETY_REFUSAL_PATTERN.search(repair.completion_text or "")
                ):
                    repaired_text = repair.completion_text
                    outcome = "refused"
                if repair.usage:
                    self.stats.token_usage += repair.usage
                    self.stats.current_context_tokens = repair.usage.input
            except Exception as exc:
                outcome = type(exc).__name__
            llm_resp.result_chain = None
            llm_resp.completion_text = repaired_text
            llm_resp.reasoning_content = None
            llm_resp.reasoning_signature = None
            llm_resp.raw_completion = None
            llm_resp.tools_call_name = []
            llm_resp.tools_call_args = []
            llm_resp.tools_call_ids = []
            llm_resp.tools_call_extra_content = {}
            if event is not None and hasattr(event, "set_extra"):
                event.set_extra("_llm_reasoning_content", None)
            logger.info(
                "Code delivery repair message_id=%s language=%s outcome=%s",
                getattr(getattr(event, "message_obj", None), "message_id", ""),
                language,
                outcome,
            )
        self.final_llm_resp = llm_resp
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

        parts = []
        if llm_resp.reasoning_content is not None or llm_resp.reasoning_signature:
            parts.append(
                ThinkPart(
                    think=llm_resp.reasoning_content or "",
                    encrypted=llm_resp.reasoning_signature,
                )
            )
        if llm_resp.completion_text:
            parts.append(TextPart(text=llm_resp.completion_text))
        if len(parts) == 0:
            logger.warning("LLM returned empty assistant message with no tool calls.")
        self.run_context.messages.append(Message(role="assistant", content=parts))

        try:
            await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)
        self._resolve_unconsumed_follow_ups()

    @override
    async def reset(
        self,
        provider: Provider,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool = False,
        # enforce max turns, will discard older turns when exceeded BEFORE compression
        # -1 means no limit
        enforce_max_turns: int = -1,
        # llm compressor
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent_ratio: float = 0.15,
        llm_compress_provider: Provider | None = None,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # customize
        custom_token_counter: TokenCounter | None = None,
        custom_compressor: ContextCompressor | None = None,
        tool_schema_mode: str | None = "full",
        hook_timing_mode: str | None = None,
        fallback_providers: list[Provider] | None = None,
        request_max_retries: int | None = None,
        tool_result_overflow_dir: str | None = None,
        read_tool: FunctionTool | None = None,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.enforce_max_turns = enforce_max_turns
        self.llm_compress_instruction = llm_compress_instruction
        self.llm_compress_keep_recent_ratio = llm_compress_keep_recent_ratio
        self.llm_compress_provider = llm_compress_provider
        self.truncate_turns = truncate_turns
        self.custom_token_counter = custom_token_counter
        self.custom_compressor = custom_compressor
        self.request_max_retries = request_max_retries
        self.tool_result_overflow_dir = tool_result_overflow_dir
        self.read_tool = read_tool
        self._tool_result_token_counter = EstimateTokenCounter()
        self.request_context_manager_config = ContextConfig(
            # <=0 disables token-based guarding.
            max_context_tokens=provider.provider_config.get("max_context_tokens", 0),
            # Enforce max turns before token-based guarding.
            enforce_max_turns=self.enforce_max_turns,
            truncate_turns=self.truncate_turns,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent_ratio=self.llm_compress_keep_recent_ratio,
            llm_compress_provider=self.llm_compress_provider,
            custom_token_counter=self.custom_token_counter,
            custom_compressor=self.custom_compressor,
        )
        self.request_context_manager = ContextManager(
            self.request_context_manager_config
        )

        self.provider = provider
        self.fallback_providers: list[Provider] = []
        seen_provider_ids: set[str] = {str(provider.provider_config.get("id", ""))}
        for fallback_provider in fallback_providers or []:
            fallback_id = str(fallback_provider.provider_config.get("id", ""))
            if fallback_provider is provider:
                continue
            if fallback_id and fallback_id in seen_provider_ids:
                continue
            self.fallback_providers.append(fallback_provider)
            if fallback_id:
                seen_provider_ids.add(fallback_id)
        self.final_llm_resp = None
        self._code_repair_attempted = False
        self._state = AgentState.IDLE
        self.tool_executor = tool_executor
        self.agent_hooks = agent_hooks
        self.run_context = run_context
        self._aborted = False
        self._abort_signal = asyncio.Event()
        self._pending_follow_ups: list[FollowUpTicket] = []
        self._follow_up_seq = 0
        self._last_tool_name: str | None = None
        self._last_tool_args: dict[str, T.Any] | None = None
        self._same_tool_streak = 0
        self._last_failed_tool_key: tuple[str, str] | None = None
        self._same_tool_failure_streak = 0
        self._repeated_failed_call_ids: list[str] = []
        self._blocked_failed_tool_keys: set[tuple[str, str]] = set()
        self._tool_failure_summary = ""
        self._proactive_request_finished = False
        # Set by astr_agent_run_util while a proactive reply is being delivered.
        self._proactive_delivery_deferred = False

        # These two are used for tool schema mode handling
        # We now have two modes:
        # - "full": use full tool schema for LLM calls, default.
        # - "skills_like": use light tool schema for LLM calls, and re-query with param-only schema when needed.
        #   Light tool schema does not include tool parameters.
        #   This can reduce token usage when tools have large descriptions.
        # See #4681
        self.tool_schema_mode = tool_schema_mode
        # "enhanced" fires the completion hook before the reply is emitted;
        # "legacy" restores the upstream timing on paths that have a counterpart.
        self.hook_timing_mode = normalize_hook_timing_mode(hook_timing_mode)
        self._tool_schema_param_set = None
        self._skill_like_raw_tool_set = None
        if tool_schema_mode == "skills_like":
            tool_set = self.req.func_tool
            if tool_set:
                self._skill_like_raw_tool_set = tool_set
                light_set = tool_set.get_light_tool_set()
                self._tool_schema_param_set = tool_set.get_param_only_tool_set()
                # MODIFIE the req.func_tool to use light tool schemas
                self.req.func_tool = light_set

        # append existing messages in the run context
        messages = bind_checkpoint_messages(request.contexts or [])
        if (
            request.prompt is not None
            or request.image_urls
            or request.audio_urls
            or request.extra_user_content_parts
        ):
            m = await self._assemble_request_context_for_provider(request)
            messages.append(Message.model_validate(m))
        if request.system_prompt:
            messages.insert(
                0,
                Message(role="system", content=request.system_prompt),
            )
        self.run_context.messages = messages

        self.stats = AgentStats()
        self.stats.start_time = time.time()

    def _read_tool_hint(self) -> str:
        return read_tool_hint(self)

    def _track_tool_call_streak(
        self,
        tool_name: str,
        tool_args: dict[str, T.Any] | None,
    ) -> int:
        return track_tool_call_streak(self, tool_name, tool_args)

    def _build_repeated_tool_call_guidance(self, tool_name: str, streak: int) -> str:
        return build_repeated_tool_call_guidance(self, tool_name, streak)

    async def _assemble_request_context_for_provider(
        self,
        request: ProviderRequest,
    ) -> dict[str, T.Any]:
        modalities = self.provider.provider_config.get("modalities", None)
        if not modalities:  # Unconfigured (None or empty list) defaults to support all modalities for backward compatibility
            return await request.assemble_context()

        supports_image = "image" in modalities
        supports_audio = "audio" in modalities
        if supports_image and supports_audio:
            return await request.assemble_context()

        adjusted_request = replace(
            request,
            image_urls=request.image_urls if supports_image else [],
            audio_urls=request.audio_urls if supports_audio else [],
        )
        context = await adjusted_request.assemble_context()
        # Materialization can fail after the earlier image preparation stage.
        # Preserve that outcome on the request checked by the runner, even when
        # unsupported audio required a provider-specific copy of the request.
        if supports_image:
            request.image_input_unavailable = adjusted_request.image_input_unavailable
        content = context.get("content")
        if isinstance(content, str):
            content_blocks: list[dict[str, T.Any]] = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            content_blocks = content
        else:
            content_blocks = []

        if not supports_image:
            for _ in request.image_urls:
                content_blocks.append({"type": "text", "text": "[Image]"})
        if not supports_audio:
            for _ in request.audio_urls:
                content_blocks.append({"type": "text", "text": "[Audio]"})

        return {"role": "user", "content": content_blocks}

    async def _write_tool_result_overflow_file(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> str:
        return await write_tool_result_overflow_file(
            self,
            tool_call_id=tool_call_id,
            content=content,
        )

    async def _materialize_large_tool_result(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> str:
        if self.tool_result_overflow_dir is None or self.read_tool is None:
            return content

        estimated_tokens = self._tool_result_token_counter.count_tokens(
            [Message(role="tool", content=content, tool_call_id=tool_call_id)]
        )
        if estimated_tokens <= self.TOOL_RESULT_MAX_ESTIMATED_TOKENS:
            return content

        preview = self._truncate_tool_result_preview(content, tool_call_id=tool_call_id)
        try:
            overflow_path = await self._write_tool_result_overflow_file(
                tool_call_id=tool_call_id,
                content=content,
            )
        except Exception as exc:
            logger.warning(
                "Failed to spill oversized tool result for %s: %s",
                tool_call_id,
                exc,
                exc_info=True,
            )
            error_notice = (
                "Tool output exceeded the inline result limit "
                f"({estimated_tokens} estimated tokens > "
                f"{self.TOOL_RESULT_MAX_ESTIMATED_TOKENS}) and could not be written "
                f"to `{self.tool_result_overflow_dir}`: {exc}"
            )
            if not preview:
                return error_notice
            return f"{preview}\n\n{error_notice}"

        notice = self.TOOL_RESULT_OVERFLOW_NOTICE_TEMPLATE.format(
            overflow_path=overflow_path,
            read_tool_hint=self._read_tool_hint(),
        )
        if not preview:
            return notice
        return f"{preview}\n\n{notice}"

    def _truncate_tool_result_preview(
        self,
        content: str,
        *,
        tool_call_id: str,
    ) -> str:
        return truncate_tool_result_preview(
            self,
            content,
            tool_call_id=tool_call_id,
        )

    async def _await_or_stop(
        self,
        awaitable: T.Awaitable[AwaitableResultT],
    ) -> AwaitableResultT | None:
        """Await work while allowing a stop request to cancel it immediately.

        Args:
            awaitable: Provider or context-processing operation to execute.

        Returns:
            The operation result, or None when user cancellation wins the race.

        Raises:
            asyncio.CancelledError: If the outer Agent task is cancelled.
            Exception: Any exception raised by the awaited operation.
        """
        operation_task = asyncio.create_task(awaitable)
        abort_task = asyncio.create_task(self._abort_signal.wait())
        try:
            done, _ = await asyncio.wait(
                {operation_task, abort_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if abort_task in done:
                if not operation_task.done():
                    operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
                return None
            return operation_task.result()
        except asyncio.CancelledError:
            if not operation_task.done():
                operation_task.cancel()
            await asyncio.gather(operation_task, return_exceptions=True)
            raise
        finally:
            if not abort_task.done():
                abort_task.cancel()
            await asyncio.gather(abort_task, return_exceptions=True)

    async def _iter_llm_responses(
        self, *, include_model: bool = True
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        payload = {
            "contexts": self._sanitize_contexts_for_provider(self.run_context.messages),
            "func_tool": self._func_tool_for_provider(),
            "session_id": self.req.session_id,
            "extra_user_content_parts": self.req.extra_user_content_parts,  # list[ContentPart]
            "abort_signal": self._abort_signal,
            "request_max_retries": self.request_max_retries,
        }
        if include_model:
            # For primary provider we keep explicit model selection if provided.
            payload["model"] = self.req.model
        if self.streaming:
            stream = self.provider.text_chat_stream(**payload)
            try:
                while True:
                    try:
                        resp = await self._await_or_stop(anext(stream))  # type: ignore
                    except StopAsyncIteration:
                        return
                    if resp is None:
                        return
                    yield resp
            finally:
                await self._close_executor(stream)
        else:
            resp = await self._await_or_stop(self.provider.text_chat(**payload))
            if resp is not None:
                yield resp

    async def _iter_llm_responses_with_fallback(
        self,
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Wrap _iter_llm_responses with provider fallback handling."""
        if not self.run_context.messages:
            logger.warning(
                "Skipping LLM request because no messages remain after agent/request "
                "hooks and context processing."
            )
            yield LLMResponse(
                role="err",
                completion_text="No messages remain for the LLM request.",
            )
            return

        candidates = [self.provider, *self.fallback_providers]
        total_candidates = len(candidates)
        last_exception: Exception | None = None
        last_err_response: LLMResponse | None = None

        for idx, candidate in enumerate(candidates):
            if self._is_stop_requested():
                return
            candidate_id = candidate.provider_config.get("id", "<unknown>")
            is_last_candidate = idx == total_candidates - 1
            if idx > 0:
                logger.warning(
                    "Switched from %s to fallback chat provider: %s",
                    self.provider.provider_config.get("id", "<unknown>"),
                    candidate_id,
                )
            self.provider = candidate
            try:
                retrying = AsyncRetrying(
                    retry=retry_if_exception_type(EmptyModelOutputError),
                    stop=stop_after_attempt(self.EMPTY_OUTPUT_RETRY_ATTEMPTS),
                    wait=wait_exponential(
                        multiplier=1,
                        min=self.EMPTY_OUTPUT_RETRY_WAIT_MIN_S,
                        max=self.EMPTY_OUTPUT_RETRY_WAIT_MAX_S,
                    ),
                    reraise=True,
                )

                async for attempt in retrying:
                    if self._is_stop_requested():
                        return
                    has_stream_output = False
                    with attempt:
                        try:
                            async for resp in self._iter_llm_responses(
                                include_model=idx == 0
                            ):
                                if resp.is_chunk:
                                    has_stream_output = True
                                    yield resp
                                    continue

                                if (
                                    resp.role == "err"
                                    and not has_stream_output
                                    and (not is_last_candidate)
                                ):
                                    last_err_response = resp
                                    logger.warning(
                                        "Chat Model %s returns error response, trying fallback to next provider.",
                                        candidate_id,
                                    )
                                    break

                                self._sanitize_malformed_tool_calls(resp)
                                yield resp
                                return

                            if has_stream_output:
                                return
                        except EmptyModelOutputError:
                            if has_stream_output:
                                logger.warning(
                                    "Chat Model %s returned empty output after streaming started; skipping empty-output retry.",
                                    candidate_id,
                                )
                            else:
                                logger.warning(
                                    "Chat Model %s returned empty output on attempt %s/%s.",
                                    candidate_id,
                                    attempt.retry_state.attempt_number,
                                    self.EMPTY_OUTPUT_RETRY_ATTEMPTS,
                                )
                            raise
                    if self._is_stop_requested():
                        return
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                logger.warning(
                    "Chat Model %s request error: %s",
                    candidate_id,
                    exc,
                    exc_info=True,
                )
                continue

        if last_err_response:
            yield last_err_response
            return
        if last_exception:
            yield LLMResponse(
                role="err",
                completion_text=(
                    "All chat models failed: "
                    f"{type(last_exception).__name__}: {last_exception}"
                ),
            )
            return
        yield LLMResponse(
            role="err",
            completion_text="All available chat models are unavailable.",
        )

    def _sanitize_contexts_for_provider(
        self,
        contexts: list[Message] | list[dict[str, T.Any]],
    ) -> list[Message] | list[dict[str, T.Any]]:
        modalities = self.provider.provider_config.get("modalities", None)
        if (
            not modalities
        ):  # Unconfigured (None or empty list) defaults to support all modalities
            return contexts
        sanitized_contexts, stats = sanitize_contexts_by_modalities(
            contexts,
            self.provider.provider_config.get("modalities", None),
        )
        log_context_sanitize_stats(stats)
        return sanitized_contexts

    def _func_tool_for_provider(self) -> ToolSet | None:
        if not self.req.func_tool:
            return None
        modalities = self.provider.provider_config.get("modalities", None)
        if isinstance(modalities, list) and modalities and "tool_use" not in modalities:
            logger.debug(
                "Provider %s does not support tool_use, clearing tools for request.",
                self.provider,
            )
            return None
        return self.req.func_tool

    def _simple_print_message_role(self, tag: str, messages: list):
        roles = [m.role for m in messages]
        n = len(roles)
        if n > 10:
            summary = ",".join(roles[:4]) + ",...," + ",".join(roles[-4:])
        else:
            summary = ",".join(roles)
        logger.debug(f"{tag} messages -> [{n}] {summary}")

    def follow_up(
        self,
        *,
        message_text: str,
    ) -> FollowUpTicket | None:
        """Queue a follow-up message for the next tool result."""
        if self.done() or self._is_stop_requested():
            return None
        text = (message_text or "").strip()
        if not text:
            return None
        ticket = FollowUpTicket(seq=self._follow_up_seq, text=text)
        self._follow_up_seq += 1
        self._pending_follow_ups.append(ticket)
        return ticket

    def _resolve_unconsumed_follow_ups(self) -> None:
        if not self._pending_follow_ups:
            return
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.resolved.set()

    def _consume_follow_up_notice(self) -> str:
        if not self._pending_follow_ups:
            return ""
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.consumed = True
            ticket.resolved.set()
        follow_up_lines = "\n".join(
            f"{idx}. {ticket.text}" for idx, ticket in enumerate(follow_ups, start=1)
        )
        return self.FOLLOW_UP_NOTICE_TEMPLATE.format(
            follow_up_lines=follow_up_lines,
        )

    def _merge_follow_up_notice(self, content: str) -> str:
        notice = self._consume_follow_up_notice()
        if not notice:
            return content
        return f"{content}{notice}"

    def _sanitize_malformed_tool_calls(
        self,
        llm_resp: LLMResponse,
    ) -> None:
        """Normalize malformed tool call names.

        Args:
            llm_resp: The LLM response whose tool call lists should be sanitized.
        """
        llm_resp.tools_call_name = [
            self.MALFORMED_TOOL_NAME_PLACEHOLDER
            if tool_name is None or tool_name.strip() == ""
            else tool_name
            for tool_name in llm_resp.tools_call_name
        ]

    @override
    async def step(self):
        """Release proactive busy state only after a terminal or interrupted step."""
        terminated = False
        try:
            async for response in self._step():
                yield response
        except BaseException:
            terminated = True
            raise
        finally:
            if terminated or self.done():
                self._finish_proactive_request()

    def _finish_proactive_request(self) -> None:
        """Notify the proactive capability owner once, even if its token is stale.

        The plugin is found by the ``finish_proactive_request`` capability
        rather than by directory name
        (see ``docs/maintained/plugin-capability-lookup.md``).
        """
        if getattr(self, "_proactive_delivery_deferred", False):
            return
        if getattr(self, "_proactive_request_finished", False):
            return
        event = getattr(getattr(self.run_context, "context", None), "event", None)
        if not event or not callable(getattr(event, "get_extra", None)):
            return
        if not event.get_extra("_enhance_active_reply_token"):
            return
        from astrbot.core.star.star import star_registry

        self._proactive_request_finished = True
        for metadata in star_registry:
            if metadata.activated and metadata.star_cls is not None:
                finish = getattr(metadata.star_cls, "finish_proactive_request", None)
                if not callable(finish):
                    continue
                try:
                    finish(event)
                except Exception as exc:
                    logger.warning(
                        "Proactive completion cleanup failed (%s).",
                        type(exc).__name__,
                    )
                return

    async def _step(self):
        """Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        if getattr(self.req, "image_input_unavailable", False):
            response = LLMResponse(
                role="assistant",
                completion_text="当前看不到图片，请重新发送。",
                image_input_unavailable=True,
            )
            await self._complete_with_assistant_response(response)
            chain = response.result_chain
            if not chain and response.completion_text:
                chain = MessageChain().message(response.completion_text)
            if chain:
                yield AgentResponse(
                    type="llm_result", data=AgentResponseData(chain=chain)
                )
                if self.streaming:
                    yield AgentResponse(
                        type="streaming_delta", data=AgentResponseData(chain=chain)
                    )
            return

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)
        llm_resp_result = None

        # Process request-time context before sending it to the provider.
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self._simple_print_message_role("[BefCompact]", self.run_context.messages)
        processed_messages = await self._await_or_stop(
            self.request_context_manager.process(
                self.run_context.messages,
                trusted_token_usage=token_usage,
            )
        )
        if processed_messages is None:
            yield await self._finalize_aborted_step()
            return
        self.run_context.messages = processed_messages
        self._simple_print_message_role("[AftCompact]", self.run_context.messages)

        async for llm_response in self._iter_llm_responses_with_fallback():
            if llm_response.is_chunk:
                if self.stats.time_to_first_token == 0:
                    self.stats.time_to_first_token = time.time() - self.stats.start_time

                if llm_response.reasoning_content:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain(type="reasoning").message(
                                llm_response.reasoning_content,
                            ),
                        ),
                    )
                if llm_response.result_chain:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=llm_response.result_chain),
                    )
                elif llm_response.completion_text:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(llm_response.completion_text),
                        ),
                    )
                if self._is_stop_requested():
                    break
                continue
            llm_resp_result = llm_response

            # Chunk responses have already continued above. A missing usage report
            # means the latest context occupancy is unknown.
            self.stats.current_context_tokens = 0
            if llm_response.usage:
                # Keep cumulative usage for billing and expose the latest request
                # input separately for context-window occupancy displays.
                self.stats.token_usage += llm_response.usage
                self.stats.current_context_tokens = llm_response.usage.input
                if self.req.conversation:
                    self.req.conversation.token_usage = llm_response.usage.total
            # end_time must be set before the yield serializes to_dict().
            self.stats.end_time = time.time()
            yield AgentResponse(
                type="agent_stats",
                data=AgentResponseData(
                    chain=MessageChain(
                        type="agent_stats",
                        chain=[Json(data=self.stats.to_dict())],
                    )
                ),
            )
            break  # got final response

        if self._is_stop_requested():
            yield await self._finalize_aborted_step()
            return

        if not llm_resp_result:
            return

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            self._resolve_unconsumed_follow_ups()
            custom_error_message = self._get_persona_custom_error_message()
            error_text = custom_error_message or (
                f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(error_text),
                ),
            )
            return

        if not llm_resp.tools_call_name:
            await self._complete_with_assistant_response(llm_resp)

        # 返回 LLM 结果
        if llm_resp.reasoning_content:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain(type="reasoning").message(
                        llm_resp.reasoning_content,
                    ),
                ),
            )
        if llm_resp.result_chain:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(chain=llm_resp.result_chain),
            )
        elif llm_resp.completion_text:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain().message(llm_resp.completion_text),
                ),
            )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            if self.tool_schema_mode == "skills_like":
                requery_resp, _ = await self._resolve_tool_exec(llm_resp)
                if self._is_stop_requested():
                    yield await self._finalize_aborted_step()
                    return
                if not requery_resp.tools_call_name:
                    llm_resp = requery_resp
                    logger.warning(
                        "skills_like tool re-query returned no tool calls; fallback to assistant response."
                    )
                    # "enhanced" (default) fires the completion hook before the
                    # reply is emitted; "legacy" defers it until right after the
                    # llm_result yields, which is where upstream calls it.
                    legacy_timing = self.hook_timing_mode == "legacy"
                    if not legacy_timing:
                        await self._complete_with_assistant_response(llm_resp)
                    if llm_resp.reasoning_content:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(
                                chain=MessageChain(type="reasoning").message(
                                    llm_resp.reasoning_content,
                                ),
                            ),
                        )
                    if llm_resp.result_chain:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(chain=llm_resp.result_chain),
                        )
                    elif llm_resp.completion_text:
                        yield AgentResponse(
                            type="llm_result",
                            data=AgentResponseData(
                                chain=MessageChain().message(llm_resp.completion_text),
                            ),
                        )

                    if legacy_timing:
                        await self._complete_with_assistant_response(llm_resp)

                    # Re-query uses text_chat(), so its reply has no stream chunks.
                    # Supply them after hooks without changing llm_result ordering.
                    if self.streaming:
                        if llm_resp.reasoning_content:
                            yield AgentResponse(
                                type="streaming_delta",
                                data=AgentResponseData(
                                    chain=MessageChain(type="reasoning").message(
                                        llm_resp.reasoning_content,
                                    ),
                                ),
                            )
                        chain = llm_resp.result_chain
                        if not chain and llm_resp.completion_text:
                            chain = MessageChain().message(llm_resp.completion_text)
                        if chain:
                            yield AgentResponse(
                                type="streaming_delta",
                                data=AgentResponseData(chain=chain),
                            )
                    return
                else:
                    llm_resp.tools_call_name = requery_resp.tools_call_name
                    llm_resp.tools_call_args = requery_resp.tools_call_args
                    llm_resp.tools_call_ids = requery_resp.tools_call_ids

            tool_call_result_blocks = []
            cached_images = []  # Collect cached images for LLM visibility
            try:
                async for result in self._handle_function_tools(self.req, llm_resp):
                    if result.kind == "tool_call_result_blocks":
                        if result.tool_call_result_blocks is not None:
                            tool_call_result_blocks = result.tool_call_result_blocks
                    elif result.kind == "cached_image":
                        if result.cached_image is not None:
                            # Collect cached image info
                            cached_images.append(result.cached_image)
                    elif result.kind == "message_chain":
                        chain = result.message_chain
                        if chain is None or chain.type is None:
                            # should not happen
                            continue
                        if chain.type == "tool_direct_result":
                            ar_type = "tool_call_result"
                        else:
                            ar_type = chain.type
                        yield AgentResponse(
                            type=ar_type,
                            data=AgentResponseData(chain=chain),
                        )
            except _ToolExecutionInterrupted:
                yield await self._finalize_aborted_step()
                return

            # 将结果添加到上下文中
            parts = []
            if llm_resp.reasoning_content is not None or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content or "",
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            if len(parts) == 0:
                parts = None
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    tool_calls=llm_resp.to_openai_tool_calls_model(),
                    content=parts,
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            # record the assistant message with tool calls
            self.run_context.messages.extend(
                tool_calls_result.to_openai_messages_model()
            )

            # If there are cached images and the model supports image input,
            # append a user message with images so LLM can see them
            if cached_images:
                modalities = self.provider.provider_config.get("modalities", [])
                supports_image = (
                    not modalities or "image" in modalities
                )  # Empty list is treated as unconfigured for backward compatibility
                if supports_image:
                    # Build user message with images for LLM to review
                    image_parts = []
                    for cached_img in cached_images:
                        img_data = tool_image_cache.get_image_base64_by_path(
                            cached_img.file_path, cached_img.mime_type
                        )
                        if img_data:
                            base64_data, mime_type = img_data
                            image_parts.append(
                                TextPart(
                                    text=f"[Image from tool '{cached_img.tool_name}', path='{cached_img.file_path}']"
                                )
                            )
                            image_parts.append(
                                ImageURLPart(
                                    image_url=ImageURLPart.ImageURL(
                                        url=f"data:{mime_type};base64,{base64_data}",
                                        id=cached_img.file_path,
                                    )
                                )
                            )
                    if image_parts:
                        self.run_context.messages.append(
                            Message(role="user", content=image_parts)
                        )
                        logger.debug(
                            f"Appended {len(cached_images)} cached image(s) to context for LLM review"
                        )

            self.req.append_tool_calls_result(tool_calls_result)
            if self._tool_failure_summary:
                # One bounded final generation replaces further agent iterations.
                # All emitted calls still have tool results, including skipped calls.
                self.req.func_tool = None
                self._skill_like_raw_tool_set = None
                self._tool_schema_param_set = None
                self.run_context.messages.append(
                    Message(
                        role="user",
                        content=(
                            "[Tool failure limit] The same tool failed three consecutive "
                            "times with the same effective arguments. Stop using tools. "
                            "Briefly explain what could not be completed and the missing "
                            "requirement. Do not claim success or repeat any action.\n"
                            + self._tool_failure_summary
                        ),
                    )
                )
                final_response = LLMResponse(
                    role="assistant",
                    completion_text="这次工具连续失败，没能完成。请补充所需参数后再试。",
                )
                try:
                    generated = await self._await_or_stop(
                        asyncio.wait_for(
                            self.provider.text_chat(
                                contexts=self._sanitize_contexts_for_provider(
                                    self.run_context.messages
                                ),
                                func_tool=None,
                                model=self.req.model,
                                session_id=self.req.session_id,
                                abort_signal=self._abort_signal,
                                request_max_retries=0,
                            ),
                            timeout=AUXILIARY_LLM_TIMEOUT_SEC,
                        )
                    )
                    if self._is_stop_requested():
                        yield await self._finalize_aborted_step()
                        return
                    if (
                        generated
                        and generated.role == "assistant"
                        and not generated.tools_call_name
                        and generated.completion_text.strip()
                    ):
                        final_response = generated
                    if generated and generated.usage:
                        self.stats.token_usage += generated.usage
                        self.stats.current_context_tokens = generated.usage.input
                except Exception as exc:
                    logger.warning(
                        "Tool failure final response failed: %s", type(exc).__name__
                    )
                await self._complete_with_assistant_response(final_response)
                chain = final_response.result_chain
                if not chain and final_response.completion_text:
                    chain = MessageChain().message(final_response.completion_text)
                if chain:
                    yield AgentResponse(
                        type="llm_result", data=AgentResponseData(chain=chain)
                    )
                    if self.streaming:
                        yield AgentResponse(
                            type="streaming_delta", data=AgentResponseData(chain=chain)
                        )
                return

    async def step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
        try:
            async for response in self._step_until_done(max_step):
                yield response
        finally:
            self._finish_proactive_request()

    async def _step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        #  如果循环结束了但是 agent 还没有完成，说明是达到了 max_step
        if not self.done():
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            # 拔掉所有工具
            if self.req:
                self.req.func_tool = None
            # 注入提示词
            self.run_context.messages.append(
                Message(
                    role="user",
                    content=self.MAX_STEPS_REACHED_PROMPT,
                )
            )
            # 再执行最后一步
            async for resp in self.step():
                yield resp

    async def _handle_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[_HandleFunctionToolsResult, None]:
        """处理函数工具调用。"""
        tool_call_result_blocks: list[ToolCallMessageSegment] = []
        logger.info(f"Agent 使用工具: {llm_response.tools_call_name}")

        def _append_tool_call_result(tool_call_id: str, content: str) -> None:
            for previous in tool_call_result_blocks:
                if previous.tool_call_id == tool_call_id:
                    previous.content = (
                        f"{previous.content}\n\n{self._merge_follow_up_notice(content)}"
                    )
                    return
            tool_call_result_blocks.append(
                ToolCallMessageSegment(
                    role="tool",
                    tool_call_id=tool_call_id,
                    content=self._merge_follow_up_notice(content),
                ),
            )

        # 执行函数调用
        for func_tool_name, func_tool_args, func_tool_id in zip(
            llm_response.tools_call_name,
            llm_response.tools_call_args,
            llm_response.tools_call_ids,
        ):
            event = getattr(self.run_context.context, "event", None)
            if not is_current(event):
                self.request_stop()
                return
            tool_result_blocks_start = len(tool_call_result_blocks)
            tool_reserved = False
            tool_call_streak = 1
            valid_params = {} if func_tool_args is None else func_tool_args
            call_failed = False
            call_blocked = False
            failure_reason = ""
            failure_key = (func_tool_name, "")
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call",
                    chain=[
                        Json(
                            data={
                                "id": func_tool_id,
                                "name": func_tool_name,
                                "args": func_tool_args,
                                "ts": time.time(),
                            }
                        )
                    ],
                )
            )
            try:
                if (
                    self.tool_schema_mode == "skills_like"
                    and self._skill_like_raw_tool_set
                ):
                    # in 'skills_like' mode, raw.func_tool is light schema, does not have handler
                    # so we need to get the tool from the raw tool set
                    func_tool = self._skill_like_raw_tool_set.get_tool(func_tool_name)
                    available_tools = self._skill_like_raw_tool_set.names()
                else:
                    func_tool = (
                        req.func_tool.get_tool(func_tool_name)
                        if req.func_tool
                        else None
                    )
                    available_tools = req.func_tool.names() if req.func_tool else []

                #  Some API may return None for tools with no parameters
                if func_tool_args is None:
                    func_tool_args = {}
                logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")

                if not func_tool:
                    logger.warning(f"未找到指定的工具: {func_tool_name}，将跳过。")
                    call_failed = True
                    failure_reason = f"Tool {func_tool_name} not found."
                    failure_key = (
                        func_tool_name,
                        json.dumps(valid_params, sort_keys=True, default=str),
                    )
                    if failure_key in self._blocked_failed_tool_keys:
                        call_blocked = True
                        _append_tool_call_result(
                            func_tool_id,
                            "error: Repeated identical tool failure; execution skipped after three failures.",
                        )
                        continue
                    _append_tool_call_result(
                        func_tool_id,
                        f"error: Tool {func_tool_name} not found. Available tools are: {', '.join(available_tools)}",
                    )
                    continue

                valid_params = {}  # 参数过滤：只传递函数实际需要的参数

                # 获取实际的 handler 函数
                if func_tool.handler:
                    logger.debug(
                        f"工具 {func_tool_name} 期望的参数: {func_tool.parameters}",
                    )
                    if func_tool.parameters and func_tool.parameters.get("properties"):
                        expected_params = set(func_tool.parameters["properties"].keys())

                        valid_params = {
                            k: v
                            for k, v in func_tool_args.items()
                            if k in expected_params
                        }

                    # 记录被忽略的参数
                    ignored_params = set(func_tool_args.keys()) - set(
                        valid_params.keys(),
                    )
                    if ignored_params:
                        logger.warning(
                            f"工具 {func_tool_name} 忽略非期望参数: {ignored_params}",
                        )
                else:
                    # 如果没有 handler（如 MCP 工具），使用所有参数
                    valid_params = func_tool_args

                normalized_params = dict(valid_params)
                for name, spec in (
                    (func_tool.parameters or {}).get("properties", {}).items()
                ):
                    if (
                        name not in normalized_params
                        and isinstance(spec, dict)
                        and "default" in spec
                    ):
                        normalized_params[name] = spec["default"]
                failure_key = (
                    func_tool_name,
                    json.dumps(normalized_params, sort_keys=True, default=str),
                )
                tool_call_streak = self._track_tool_call_streak(
                    func_tool_name, normalized_params
                )
                if failure_key in self._blocked_failed_tool_keys:
                    call_blocked = True
                    _append_tool_call_result(
                        func_tool_id,
                        "error: Repeated identical tool failure; execution skipped after three failures.",
                    )
                    continue
                missing = [
                    name
                    for name in (func_tool.parameters or {}).get("required", [])
                    if name not in valid_params
                ]
                if missing:
                    raise ValueError(
                        f"Missing required tool arguments: {', '.join(missing)}"
                    )

                if not is_current(event):
                    self.request_stop()
                    return
                found, cached_result = get_tool_result(
                    event, func_tool_name, normalized_params
                )
                if not found:
                    tool_reserved = begin_tool(event, func_tool_name, normalized_params)
                    if not tool_reserved:
                        cached_result = await wait_tool_result(
                            event, func_tool_name, normalized_params
                        )
                        found = True
                if found:
                    _append_tool_call_result(func_tool_id, cached_result)
                    continue

                try:
                    await self.agent_hooks.on_tool_start(
                        self.run_context,
                        func_tool,
                        valid_params,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_start hook: {e}", exc_info=True)

                if not is_current(event):
                    release_tool(event, func_tool_name, normalized_params)
                    tool_reserved = False
                    self.request_stop()
                    return

                executor = self.tool_executor.execute(
                    tool=func_tool,
                    run_context=self.run_context,
                    **valid_params,  # 只传递有效的参数
                )

                _final_resp: CallToolResult | None = None
                async for resp in self._iter_tool_executor_results(executor):  # type: ignore
                    if isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                        result_text = "\n".join(
                            item.text
                            for item in res.content
                            if isinstance(item, TextContent)
                        )
                        if res.isError or re.match(
                            r"\s*(?:error\s*:|error (?:executing|managing)|failed\s*:)",
                            result_text,
                            re.I,
                        ):
                            call_failed = True
                            failure_reason = (
                                result_text[:600] or "Tool reported an error."
                            )
                            _append_tool_call_result(
                                func_tool_id, f"error: {failure_reason}"
                            )
                            continue
                        if not res.content:
                            call_failed = True
                            failure_reason = "The tool returned no content."
                            _append_tool_call_result(
                                func_tool_id,
                                "The tool returned no content.",
                            )
                            continue

                        result_parts: list[str] = []
                        for index, content_item in enumerate(res.content):
                            if isinstance(content_item, TextContent):
                                result_parts.append(content_item.text)
                            elif isinstance(content_item, ImageContent):
                                # Cache the image instead of sending directly
                                cached_img = tool_image_cache.save_image(
                                    base64_data=content_item.data,
                                    tool_call_id=func_tool_id,
                                    tool_name=func_tool_name,
                                    index=index,
                                    mime_type=content_item.mimeType or "image/png",
                                )
                                result_parts.append(
                                    f"Image returned and cached at path='{cached_img.file_path}'. "
                                    f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                    f"with type='image' and path='{cached_img.file_path}'."
                                )
                                # Yield image info for LLM visibility (will be handled in step())
                                yield _HandleFunctionToolsResult.from_cached_image(
                                    cached_img
                                )
                            elif isinstance(content_item, EmbeddedResource):
                                resource = content_item.resource
                                if isinstance(resource, TextResourceContents):
                                    result_parts.append(resource.text)
                                elif (
                                    isinstance(resource, BlobResourceContents)
                                    and resource.mimeType
                                    and resource.mimeType.startswith("image/")
                                ):
                                    # Cache the image instead of sending directly
                                    cached_img = tool_image_cache.save_image(
                                        base64_data=resource.blob,
                                        tool_call_id=func_tool_id,
                                        tool_name=func_tool_name,
                                        index=index,
                                        mime_type=resource.mimeType,
                                    )
                                    result_parts.append(
                                        f"Image returned and cached at path='{cached_img.file_path}'. "
                                        f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                        f"with type='image' and path='{cached_img.file_path}'."
                                    )
                                    # Yield image info for LLM visibility
                                    yield _HandleFunctionToolsResult.from_cached_image(
                                        cached_img
                                    )
                                else:
                                    result_parts.append(
                                        "The tool has returned a data type that is not supported."
                                    )
                        if result_parts:
                            inline_result = "\n\n".join(result_parts)
                            inline_result = await self._materialize_large_tool_result(
                                tool_call_id=func_tool_id,
                                content=inline_result,
                            )
                            _append_tool_call_result(
                                func_tool_id,
                                inline_result
                                + self._build_repeated_tool_call_guidance(
                                    func_tool_name, tool_call_streak
                                ),
                            )

                    elif resp is None:
                        # Tool 直接请求发送消息给用户
                        # 这里我们将直接结束 Agent Loop
                        # 发送消息逻辑在 ToolExecutor 中处理了
                        logger.warning(
                            f"{func_tool_name} 没有返回值，或者已将结果直接发送给用户。"
                        )
                        self._transition_state(AgentState.DONE)
                        self.stats.end_time = time.time()
                        _append_tool_call_result(
                            func_tool_id,
                            "The tool has no return value, or has sent the result directly to the user."
                            + self._build_repeated_tool_call_guidance(
                                func_tool_name, tool_call_streak
                            ),
                        )
                    else:
                        call_failed = True
                        failure_reason = "The tool returned an unsupported type."
                        # 不应该出现其他类型
                        logger.warning(
                            f"Tool 返回了不支持的类型: {type(resp)}。",
                        )
                        _append_tool_call_result(
                            func_tool_id,
                            "*The tool has returned an unsupported type. Please tell the user to check the definition and implementation of this tool.*"
                            + self._build_repeated_tool_call_guidance(
                                func_tool_name, tool_call_streak
                            ),
                        )

                try:
                    await self.agent_hooks.on_tool_end(
                        self.run_context,
                        func_tool,
                        func_tool_args,
                        _final_resp,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_end hook: {e}", exc_info=True)
            except Exception as e:
                if isinstance(e, _ToolExecutionInterrupted):
                    raise
                logger.warning(traceback.format_exc())
                call_failed = True
                failure_reason = str(e)[:600]
                _append_tool_call_result(
                    func_tool_id,
                    f"error: {failure_reason}"
                    + self._build_repeated_tool_call_guidance(
                        func_tool_name, tool_call_streak
                    ),
                )
            finally:
                if tool_reserved:
                    content = (
                        str(tool_call_result_blocks[-1].content)
                        if len(tool_call_result_blocks) > tool_result_blocks_start
                        else "Tool execution ended without a confirmed result. Do not repeat the action."
                    )
                    record_tool_result(
                        event, func_tool_name, normalized_params, content
                    )
                if not call_blocked:
                    if call_failed:
                        if failure_key == self._last_failed_tool_key:
                            self._same_tool_failure_streak += 1
                        else:
                            self._last_failed_tool_key = failure_key
                            self._same_tool_failure_streak = 1
                            self._repeated_failed_call_ids = []
                        self._repeated_failed_call_ids.append(func_tool_id)
                        if (
                            self._same_tool_failure_streak
                            >= self.REPEATED_TOOL_FAILURE_LIMIT
                        ):
                            self._blocked_failed_tool_keys.add(failure_key)
                            self._tool_failure_summary = (
                                f"{func_tool_name}: {failure_reason[:300]}"
                            )
                            failed_ids = set(self._repeated_failed_call_ids)
                            # Shorten result bodies, never remove one side of a pair.
                            for previous in self.run_context.messages:
                                if (
                                    previous.role == "tool"
                                    and previous.tool_call_id in failed_ids
                                ):
                                    old = str(previous.content)
                                    if "[SYSTEM NOTICE]" not in old:
                                        previous.content = "error: Repeated identical tool failure (details in final summary)."
                            for previous in tool_call_result_blocks:
                                if (
                                    previous.tool_call_id in failed_ids
                                    and "[SYSTEM NOTICE]" not in str(previous.content)
                                ):
                                    previous.content = "error: Repeated identical tool failure (details in final summary)."
                            logger.warning(
                                "Tool failure limit reached: tool=%s failures=%s",
                                func_tool_name,
                                self._same_tool_failure_streak,
                            )
                    else:
                        self._last_failed_tool_key = None
                        self._same_tool_failure_streak = 0
                        self._repeated_failed_call_ids = []

            if len(tool_call_result_blocks) > tool_result_blocks_start:
                tool_result_content = str(tool_call_result_blocks[-1].content)
                yield _HandleFunctionToolsResult.from_message_chain(
                    MessageChain(
                        type="tool_call_result",
                        chain=[
                            Json(
                                data={
                                    "id": func_tool_id,
                                    "ts": time.time(),
                                    "result": tool_result_content,
                                }
                            )
                        ],
                    )
                )
                logger.info(f"Tool `{func_tool_name}` Result: {tool_result_content}")

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield _HandleFunctionToolsResult.from_tool_call_result_blocks(
                tool_call_result_blocks
            )

    def _build_tool_requery_context(
        self,
        tool_names: list[str],
        extra_instruction: str | None = None,
    ) -> list[dict[str, T.Any]]:
        """Build contexts for re-querying LLM with param-only tool schemas."""
        contexts: list[dict[str, T.Any]] = []
        for msg in self.run_context.messages:
            if hasattr(msg, "model_dump"):
                contexts.append(msg.model_dump())  # type: ignore[call-arg]
            elif isinstance(msg, dict):
                contexts.append(copy.deepcopy(msg))
        instruction = self.SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE.format(
            tool_names=", ".join(tool_names)
        )
        if extra_instruction:
            instruction = f"{instruction}\n{extra_instruction}"
        contexts.append({"role": "user", "content": instruction})
        return contexts

    @staticmethod
    def _has_meaningful_assistant_reply(llm_resp: LLMResponse) -> bool:
        text = (llm_resp.completion_text or "").strip()
        return bool(text)

    def _build_tool_subset(self, tool_set: ToolSet, tool_names: list[str]) -> ToolSet:
        """Build a subset of tools from the given tool set based on tool names."""
        subset = ToolSet()
        for name in tool_names:
            tool = tool_set.get_tool(name)
            if tool:
                subset.add_tool(tool)
        return subset

    async def _resolve_tool_exec(
        self,
        llm_resp: LLMResponse,
    ) -> tuple[LLMResponse, ToolSet | None]:
        """Used in 'skills_like' tool schema mode to re-query LLM with param-only tool schemas."""
        tool_names = llm_resp.tools_call_name
        if not tool_names:
            return llm_resp, self.req.func_tool
        full_tool_set = self.req.func_tool
        if not isinstance(full_tool_set, ToolSet):
            return llm_resp, self.req.func_tool

        subset = self._build_tool_subset(full_tool_set, tool_names)
        if not subset.tools:
            return llm_resp, full_tool_set

        if isinstance(self._tool_schema_param_set, ToolSet):
            param_subset = self._build_tool_subset(
                self._tool_schema_param_set, tool_names
            )
            if param_subset.tools and tool_names:
                contexts = self._build_tool_requery_context(tool_names)
                requery_resp = await self._await_or_stop(
                    self.provider.text_chat(
                        contexts=self._sanitize_contexts_for_provider(contexts),
                        func_tool=param_subset,
                        model=self.req.model,
                        session_id=self.req.session_id,
                        extra_user_content_parts=self.req.extra_user_content_parts,
                        # tool_choice="required",
                        abort_signal=self._abort_signal,
                        request_max_retries=self.request_max_retries,
                    )
                )
                if requery_resp:
                    llm_resp = requery_resp
                    self._sanitize_malformed_tool_calls(llm_resp)

                # If the re-query still returns no tool calls, and also does not have a meaningful assistant reply,
                # we consider it as a failure of the LLM to follow the tool-use instruction,
                # and we will retry once with a stronger instruction that explicitly requires the LLM to either call the tool or give an explanation.
                if (
                    not llm_resp.tools_call_name
                    and not self._has_meaningful_assistant_reply(llm_resp)
                ):
                    logger.warning(
                        "skills_like tool re-query returned no tool calls and no explanation; retrying with stronger instruction."
                    )
                    repair_contexts = self._build_tool_requery_context(
                        tool_names,
                        extra_instruction=self.SKILLS_LIKE_REQUERY_REPAIR_INSTRUCTION,
                    )
                    repair_resp = await self._await_or_stop(
                        self.provider.text_chat(
                            contexts=self._sanitize_contexts_for_provider(
                                repair_contexts
                            ),
                            func_tool=param_subset,
                            model=self.req.model,
                            session_id=self.req.session_id,
                            extra_user_content_parts=self.req.extra_user_content_parts,
                            # tool_choice="required",
                            abort_signal=self._abort_signal,
                            request_max_retries=self.request_max_retries,
                        )
                    )
                    if repair_resp:
                        llm_resp = repair_resp
                        self._sanitize_malformed_tool_calls(llm_resp)

        return llm_resp, subset

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def request_stop(self) -> None:
        self._abort_signal.set()

    def _is_stop_requested(self) -> bool:
        event = getattr(self.run_context.context, "event", None)
        return self._abort_signal.is_set() or (
            event is not None and not is_current(event)
        )

    def was_aborted(self) -> bool:
        return self._aborted

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp

    async def _finalize_aborted_step(self) -> AgentResponse:
        logger.info("Agent execution was requested to stop by user.")

        self.run_context.messages.extend(
            [
                Message(
                    role="user",
                    content=[TextPart(text=self.USER_INTERRUPTION_REQUEST)],
                ),
                Message(
                    role="assistant",
                    content=[TextPart(text=self.USER_INTERRUPTION_MESSAGE)],
                ),
            ]
        )

        interrupted_resp = LLMResponse(
            role="assistant",
            completion_text=self.USER_INTERRUPTION_MESSAGE,
        )
        self.final_llm_resp = interrupted_resp
        self._aborted = True
        self._transition_state(AgentState.DONE)
        self.stats.end_time = time.time()

        try:
            await self.agent_hooks.on_agent_done(self.run_context, interrupted_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

        self._resolve_unconsumed_follow_ups()
        return AgentResponse(
            type="aborted",
            data=AgentResponseData(chain=MessageChain(type="aborted")),
        )

    async def _close_executor(self, executor: T.Any) -> None:
        close_executor = getattr(executor, "aclose", None)
        if close_executor is None:
            return
        with suppress(asyncio.CancelledError, RuntimeError, StopAsyncIteration):
            await close_executor()


    async def _iter_tool_executor_results(
        self,
        executor: T.AsyncGenerator[ToolExecutorResultT, None],
    ) -> T.AsyncGenerator[ToolExecutorResultT, None]:
        async for result in iter_tool_executor_results(self, executor):
            yield result

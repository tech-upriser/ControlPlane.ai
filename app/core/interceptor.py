import json
import time
import uuid
from typing import AsyncGenerator, List, Optional

from app.checkers.pii_scanner import scan_text, redact_text
from app.checkers.injection_detector import detect_injection
from app.checkers.content_safety import check_content_safety
from app.checkers.hallucination_checker import check_hallucination
from app.checkers.loop_breaker import detect_loop
from app.checkers.context_health import calculate_health, calculate_cost_metrics
from app.core.risk_engine import RiskEngine
from app.core.policy import PolicyProfile
from app.core.telemetry import AuditLogger, RuleTriggered
from app.core.session import SessionStore


class InputShieldResult:
    """Result of pre-LLM input scanning."""
    def __init__(self, blocked: bool, action: str, reasons: List[str], risk_scores: Optional[dict] = None):
        self.blocked = blocked
        self.action = action  # "allow", "block"
        self.reasons = reasons
        self.risk_scores = risk_scores


class StreamInterceptor:
    BUFFER_SIZE = 50  # tokens before flushing

    def __init__(
        self,
        policy: PolicyProfile,
        session_store: SessionStore,
        audit_logger: AuditLogger,
        risk_engine: RiskEngine,
        session_id: str,
        original_prompt: str,
        model: str = "mock",
    ):
        self.policy = policy
        self.session_store = session_store
        self.audit_logger = audit_logger
        self.risk_engine = risk_engine
        self.session_id = session_id
        self.original_prompt = original_prompt
        self.model = model
        self.request_id = str(uuid.uuid4())
        self.token_buffer: List[str] = []
        self.full_response = ""
        self.token_count = 0

    def scan_input(self, messages: list) -> InputShieldResult:
        """Input Shield: scan incoming messages BEFORE they reach the LLM.
        Checks the last user message for PII, injection, and unsafe content."""
        # Extract the last user message
        user_text = ""
        for msg in reversed(messages):
            if hasattr(msg, 'role') and msg.role == 'user' and msg.content:
                user_text = msg.content
                break
            elif isinstance(msg, dict) and msg.get('role') == 'user' and msg.get('content'):
                user_text = msg['content']
                break

        if not user_text:
            return InputShieldResult(blocked=False, action="allow", reasons=[])

        reasons = []
        start_time = time.time()

        # Check injection
        injection_result = detect_injection(user_text)
        if injection_result.is_injection:
            if self.policy.injection_action == "block":
                reasons.append(f"Prompt injection detected: {injection_result.injection_type}")
                # Log audit event
                self._log_input_shield_event("block", ["injection_detector"], reasons, time.time() - start_time)
                return InputShieldResult(blocked=True, action="block", reasons=reasons)
            elif self.policy.injection_action == "flag":
                reasons.append(f"Prompt injection flagged: {injection_result.injection_type}")

        # Check PII in input
        pii_matches = scan_text(user_text)
        if pii_matches:
            if self.policy.pii_action == "block":
                reasons.append(f"PII detected in input: {len(pii_matches)} match(es)")
                self._log_input_shield_event("block", ["pii_scanner"], reasons, time.time() - start_time)
                return InputShieldResult(blocked=True, action="block", reasons=reasons)
            elif self.policy.pii_action == "flag":
                reasons.append(f"PII flagged in input: {len(pii_matches)} match(es)")

        # Check content safety
        safety_result = check_content_safety(user_text)
        if not safety_result.is_safe:
            if self.policy.content_safety_action == "block":
                reasons.append(f"Unsafe content in input: {', '.join(safety_result.categories_flagged)}")
                self._log_input_shield_event("block", ["content_safety"], reasons, time.time() - start_time)
                return InputShieldResult(blocked=True, action="block", reasons=reasons)
            elif self.policy.content_safety_action == "flag":
                reasons.append(f"Unsafe content flagged: {', '.join(safety_result.categories_flagged)}")

        return InputShieldResult(blocked=False, action="allow", reasons=reasons)

    async def intercept_stream(
        self, raw_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[str, None]:
        """Wraps the raw LLM stream, buffers tokens, runs checkers, and applies actions."""
        start_time = time.time()
        checkers_used = []

        async for chunk_str in raw_stream:
            # Parse SSE chunk
            if not chunk_str.startswith("data: "):
                yield chunk_str
                continue

            data_part = chunk_str[len("data: "):].strip()

            if data_part == "[DONE]":
                # Final flush of buffer before [DONE]
                if self.token_buffer:
                    result = self._analyze_buffer()
                    checkers_used = result.get("checkers", [])
                    action = result.get("action", "allow")

                    if action == "block":
                        yield self._make_block_chunk(result.get("reasons", []))
                        return
                    elif action == "escalate":
                        yield self._make_escalate_chunk(result.get("reasons", []))
                        return

                    buffer_text = "".join(self.token_buffer)
                    if action == "reword":
                        yield self._make_reword_chunk(result.get("reasons", []))
                        return

                    # Apply PII redaction if needed
                    buffer_text = self._maybe_redact(buffer_text)
                    if action == "flag":
                        yield self._make_flag_comment(result.get("reasons", []), result.get("risk_scores", {}))

                    # Yield buffered tokens
                    for token in self.token_buffer:
                        yield self._rebuild_chunk(token)
                    self.token_buffer.clear()

                # Log final audit event
                latency = (time.time() - start_time) * 1000
                self._log_stream_event("allow", checkers_used, [], latency)

                # Update session
                self.session_store.update_session(
                    self.session_id,
                    token_delta=self.token_count,
                    action_text=self.full_response[:200],
                )

                yield chunk_str  # yield [DONE]
                return

            # Parse JSON chunk
            try:
                chunk_data = json.loads(data_part)
            except json.JSONDecodeError:
                yield chunk_str
                continue

            # Extract token content
            choices = chunk_data.get("choices", [])
            if not choices:
                yield chunk_str
                continue

            delta = choices[0].get("delta", {})
            content = delta.get("content")
            tool_calls = delta.get("tool_calls")
            finish_reason = choices[0].get("finish_reason")

            # Handle tool calls — pass through (airlock handles separately)
            if tool_calls:
                yield chunk_str
                continue

            if content:
                self.token_buffer.append(content)
                self.full_response += content
                self.token_count += 1

                # Check if buffer is full
                if len(self.token_buffer) >= self.BUFFER_SIZE or self._is_sentence_boundary(content):
                    result = self._analyze_buffer()
                    checkers_used = result.get("checkers", [])
                    action = result.get("action", "allow")

                    if action == "block":
                        latency = (time.time() - start_time) * 1000
                        self._log_stream_event("block", checkers_used, result.get("reasons", []), latency)
                        yield self._make_block_chunk(result.get("reasons", []))
                        return
                    elif action == "escalate":
                        latency = (time.time() - start_time) * 1000
                        self._log_stream_event("escalate", checkers_used, result.get("reasons", []), latency)
                        yield self._make_escalate_chunk(result.get("reasons", []))
                        return
                    elif action == "reword":
                        latency = (time.time() - start_time) * 1000
                        self._log_stream_event("reword", checkers_used, result.get("reasons", []), latency)
                        yield self._make_reword_chunk(result.get("reasons", []))
                        return

                    buffer_text = "".join(self.token_buffer)
                    buffer_text = self._maybe_redact(buffer_text)

                    if action == "flag":
                        yield self._make_flag_comment(result.get("reasons", []), result.get("risk_scores", {}))

                    # Yield individual tokens (possibly redacted)
                    if buffer_text != "".join(self.token_buffer):
                        # Text was redacted — yield as single chunk
                        yield self._rebuild_chunk(buffer_text)
                    else:
                        for token in self.token_buffer:
                            yield self._rebuild_chunk(token)
                    self.token_buffer.clear()
            elif finish_reason:
                yield chunk_str

    def _analyze_buffer(self) -> dict:
        """Run all checkers on the current buffer and return risk assessment."""
        buffer_text = "".join(self.token_buffer)
        checker_results = {}
        checkers_used = []

        # PII scan
        pii_matches = scan_text(buffer_text)
        if pii_matches:
            checker_results["pii"] = pii_matches
        checkers_used.append("pii_scanner")

        # Injection detection
        injection = detect_injection(buffer_text)
        checker_results["injection"] = injection
        checkers_used.append("injection_detector")

        # Content safety
        safety = check_content_safety(buffer_text)
        checker_results["content_safety"] = safety
        checkers_used.append("content_safety")

        # Hallucination check
        hallucination = check_hallucination(buffer_text, self.original_prompt)
        checker_results["hallucination"] = hallucination
        checkers_used.append("hallucination_checker")

        # Context health + cost (from session)
        session = self.session_store.get_session(self.session_id)
        if session:
            health = calculate_health(
                turn_count=session.turn_count,
                cumulative_tokens=session.cumulative_tokens + self.token_count,
                error_count=session.error_count,
                recent_scores=session.recent_health_scores,
                threshold=self.policy.context_health_threshold,
            )
            checker_results["context_health"] = health
            checkers_used.append("context_health")

            cost = calculate_cost_metrics(
                total_tokens=session.cumulative_tokens + self.token_count,
                loop_tokens=session.tokens_wasted_on_loops,
                model=self.model,
            )
            checker_results["cost"] = cost

            # Loop detection
            if session.action_history_texts:
                loop_result = detect_loop(
                    action_history=session.action_history_texts + [buffer_text],
                    window_size=self.policy.loop_detection_window,
                    threshold=self.policy.loop_similarity_threshold,
                )
                checker_results["loop"] = loop_result
                checkers_used.append("loop_breaker")

        # Run risk engine
        risk_scores = self.risk_engine.evaluate(checker_results, self.policy)

        return {
            "action": risk_scores.recommended_action,
            "reasons": risk_scores.triggered_reasons,
            "risk_scores": {
                "performance": risk_scores.performance_score,
                "cost": risk_scores.cost_score,
                "responsibility": risk_scores.responsibility_score,
                "overall": risk_scores.overall_risk,
            },
            "checkers": checkers_used,
            "checker_results": checker_results,
        }

    def _maybe_redact(self, text: str) -> str:
        """Apply PII redaction if policy says redact."""
        if self.policy.pii_action == "redact":
            matches = scan_text(text)
            if matches:
                return redact_text(text, matches)
        return text

    @staticmethod
    def _is_sentence_boundary(token: str) -> bool:
        """Check if token ends with sentence-ending punctuation."""
        return token.rstrip().endswith(('.', '!', '?', '\n'))

    def _rebuild_chunk(self, content: str) -> str:
        """Build an SSE chunk string with the given content."""
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    def _make_block_chunk(self, reasons: List[str]) -> str:
        """Create an SSE chunk indicating the stream was blocked."""
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"[BLOCKED] {'; '.join(reasons)}"},
                "finish_reason": "content_filter",
            }],
            "controlplane": {"action": "block", "reasons": reasons},
        }
        return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"

    def _make_reword_chunk(self, reasons: List[str]) -> str:
        """Create an SSE chunk suggesting the user reword their request."""
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"[REWORD SUGGESTED] Please rephrase your request. Reasons: {'; '.join(reasons)}"},
                "finish_reason": "content_filter",
            }],
            "controlplane": {"action": "reword", "reasons": reasons},
        }
        return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"

    def _make_escalate_chunk(self, reasons: List[str]) -> str:
        """Create an SSE chunk indicating escalation is required."""
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"[ESCALATED] Human approval required. Reasons: {'; '.join(reasons)}"},
                "finish_reason": "content_filter",
            }],
            "controlplane": {"action": "escalate", "reasons": reasons},
        }
        return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"

    def _make_flag_comment(self, reasons: List[str], risk_scores: dict) -> str:
        """Create an SSE comment with risk metadata (not a data chunk)."""
        comment_data = {"action": "flag", "reasons": reasons, "risk_scores": risk_scores}
        return f": controlplane {json.dumps(comment_data)}\n\n"

    def _log_input_shield_event(self, action: str, checkers: List[str], reasons: List[str], latency_ms: float):
        """Log an audit event for input shield actions."""
        rules = [
            RuleTriggered(checker=c, category="input_shield", action_taken=action, confidence=1.0)
            for c in checkers
        ]
        session = self.session_store.get_session(self.session_id)
        turn = session.turn_count if session else 0

        event = self.audit_logger.create_event(
            session_id=self.session_id,
            request_id=self.request_id,
            policy_profile=self.policy.name,
            latency_ms=latency_ms,
            checkers=checkers,
            rules=rules,
            risk_scores=None,
            final_action=action,
            health_score=None,
            turn=turn,
            tokens=0,
        )
        self.audit_logger.log_event(event)

    def _log_stream_event(self, action: str, checkers: List[str], reasons: List[str], latency_ms: float):
        """Log an audit event for stream interception."""
        rules = [
            RuleTriggered(checker=c, category="stream", action_taken=action, confidence=1.0)
            for c in checkers
        ]
        session = self.session_store.get_session(self.session_id)
        turn = session.turn_count if session else 0

        event = self.audit_logger.create_event(
            session_id=self.session_id,
            request_id=self.request_id,
            policy_profile=self.policy.name,
            latency_ms=latency_ms,
            checkers=checkers,
            rules=rules,
            risk_scores=None,
            final_action=action,
            health_score=None,
            turn=turn,
            tokens=self.token_count,
        )
        self.audit_logger.log_event(event)

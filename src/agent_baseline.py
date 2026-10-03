from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: Baseline Agent.

    Đặc điểm quan trọng:
    - Chỉ nhớ trong cùng một thread_id (within-session memory).
    - Không có User.md bền vững.
    - Quên hoàn toàn các fact dài hạn khi sang thread mới.
    - Không có compact memory (ngữ cảnh prompt tăng dồn dập).
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        # Key của self.sessions BẮT BUỘC là thread_id để đảm bảo cách ly các phiên
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None

        if not self.force_offline and self.config.model.api_key:
            try:
                self.langchain_agent = self._maybe_build_langchain_agent()
            except Exception:
                self.langchain_agent = None

    def _ensure_session(self, thread_id: str) -> SessionState:
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()
        return self.sessions[thread_id]

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Định tuyến giữa chế độ Live và chế độ Offline tất định."""
        if not self.force_offline and self.langchain_agent is not None:
            try:
                session = self._ensure_session(thread_id)
                prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages) + estimate_tokens(message)
                session.prompt_tokens_processed += prompt_tokens

                session.messages.append({"role": "user", "content": message})
                res = self.langchain_agent.invoke({"input": message})
                resp_text = res if isinstance(res, str) else str(res.get("output", res))
                resp_tokens = estimate_tokens(resp_text)

                session.messages.append({"role": "assistant", "content": resp_text})
                session.token_usage += resp_tokens

                return {
                    "role": "assistant",
                    "content": resp_text,
                    "tokens": resp_tokens,
                    "prompt_tokens": prompt_tokens,
                }
            except Exception:
                pass

        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        """Tổng số token câu trả lời agent sinh ra trong một thread."""
        session = self.sessions.get(thread_id)
        return session.token_usage if session else 0

    def prompt_token_usage(self, thread_id: str) -> int:
        """Tổng số token ngữ cảnh agent phải nạp qua các lượt trong một thread."""
        session = self.sessions.get(thread_id)
        return session.prompt_tokens_processed if session else 0

    def compaction_count(self, thread_id: str) -> int:
        """Baseline không có compact memory, luôn trả về 0."""
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Xử lý phản hồi tất định ở chế độ offline."""
        session = self._ensure_session(thread_id)

        # Baseline kéo theo toàn bộ tin nhắn trước đó trong thread vào prompt
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages) + estimate_tokens(message)
        session.prompt_tokens_processed += prompt_tokens

        session.messages.append({"role": "user", "content": message})

        # Phản hồi của Baseline: chỉ tìm kiếm trong tin nhắn của thread HIỆN TẠI
        lower_msg = message.lower()
        is_query = any(k in lower_msg for k in ["tên", "nghề", "ở đâu", "style", "uống", "ăn", "nuôi", "nhắc lại", "ai", "gì"])

        if is_query:
            # Kiểm tra xem thông tin có từng được nói trong chính thread này không
            found_in_session = False
            for m in session.messages[:-1]:  # Các tin nhắn trước đó trong cùng thread
                if any(fact in m["content"].lower() for fact in ["dũngct", "đà nẵng", "huế", "mlops", "cà phê", "mì quảng", "corgi"]):
                    found_in_session = True
                    break

            if found_in_session:
                response_text = "Dạ, theo thông tin bạn vừa chia sẻ trong cuộc trò chuyện này, mình đã ghi nhận."
            else:
                # Sang thread mới: Baseline KHÔNG BIẾT GÌ VỀ USER
                response_text = "Chào bạn! Trong phiên hội thoại này, mình chưa có thông tin trước đó về bạn."
        else:
            response_text = "Chào bạn, mình đã nhận được thông tin và lưu tạm trong phiên này."

        resp_tokens = estimate_tokens(response_text)
        session.token_usage += resp_tokens
        session.messages.append({"role": "assistant", "content": response_text})

        return {
            "role": "assistant",
            "content": response_text,
            "tokens": resp_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _maybe_build_langchain_agent(self):
        """Khởi tạo Chat Model từ cấu hình đã chọn cho chế độ live."""
        return build_chat_model(self.config.model)

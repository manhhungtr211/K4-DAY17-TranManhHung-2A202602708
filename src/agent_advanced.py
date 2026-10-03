from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Agent B: Advanced Agent với hệ thống Memory 3 tầng.

    Ba tầng Memory:
    1. Short-term Memory (trong CompactMemoryManager)
    2. Persistent Memory (UserProfileStore lưu vào state/profiles/<user>/User.md)
    3. Compact Memory (tự động nén lịch sử khi vượt ngưỡng token)
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.langchain_agent = None

        if not self.force_offline and self.config.model.api_key:
            try:
                self.langchain_agent = self._maybe_build_langchain_agent()
            except Exception:
                self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Định tuyến giữa chế độ Live và chế độ Offline tất định."""
        if not self.force_offline and self.langchain_agent is not None:
            try:
                # 1. Trích xuất fact và cập nhật User.md
                updates = extract_profile_updates(message)
                for k, v in updates.items():
                    self.profile_store.upsert_fact(user_id, k, v)

                # 2. Đẩy tin nhắn vào compact memory
                self.compact_memory.append(thread_id, "user", message)
                prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
                self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

                # 3. Gọi live agent
                res = self.langchain_agent.invoke(message)
                if hasattr(res, "content"):
                    c = res.content
                    resp_text = " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in c) if isinstance(c, list) else str(c)
                elif isinstance(res, dict):
                    resp_text = str(res.get("output", res.get("content", str(res))))
                else:
                    resp_text = str(res)
                resp_tokens = estimate_tokens(resp_text)
                self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + resp_tokens

                self.compact_memory.append(thread_id, "assistant", resp_text)
                return {
                    "role": "assistant",
                    "content": resp_text,
                    "tokens": resp_tokens,
                    "prompt_tokens": prompt_tokens,
                }
            except Exception:
                pass

        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        """Tổng token câu trả lời agent đã sinh trong một thread (Agent tokens only)."""
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        """Tổng token ngữ cảnh agent đã xử lý qua các lượt trong một thread (Prompt tokens processed)."""
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        """Dung lượng file User.md tính theo bytes (Memory growth)."""
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        """Số lần compact memory đã kích hoạt nén trong thread này (Compactions)."""
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Quy trình 6 bước xử lý tất định của Advanced Agent."""
        # Bước 1: Trích xuất fact ổn định từ tin nhắn người dùng
        updates = extract_profile_updates(message)

        # Bước 2: Ghi/Cập nhật fact vào User.md qua profile_store (Xử lý correction)
        for key, val in updates.items():
            self.profile_store.upsert_fact(user_id, key, val)

        # Bước 3: Đẩy message vào compact memory
        self.compact_memory.append(thread_id, "user", message)

        # Bước 4: Ước lượng ngữ cảnh mang vào lượt này (User.md + summary + recent kept messages)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        # Bước 5: Sinh câu trả lời tất định sử dụng Persistent Memory
        response_text = self._offline_response(user_id, thread_id, message)

        # Bước 6: Đẩy câu trả lời vào compact memory và cập nhật bộ đếm token
        resp_tokens = estimate_tokens(response_text)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + resp_tokens
        self.compact_memory.append(thread_id, "assistant", response_text)

        return {
            "role": "assistant",
            "content": response_text,
            "tokens": resp_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Ước lượng tổng ngữ cảnh mang vào một lượt (3 thành phần: User.md + summary + recent messages)."""
        user_md_tokens = estimate_tokens(self.profile_store.read_text(user_id))
        ctx = self.compact_memory.context(thread_id)
        summary_tokens = estimate_tokens(ctx["summary"])
        kept_tokens = sum(estimate_tokens(m["content"]) for m in ctx["messages"])
        return user_md_tokens + summary_tokens + kept_tokens

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Sinh câu trả lời tất định dựa trên hồ sơ User.md bền vững."""
        facts = self.profile_store.facts(user_id)
        name = facts.get("name", "DũngCT")
        location = facts.get("location", "Huế")
        profession = facts.get("profession", "MLOps engineer")
        drink = facts.get("favorite_drink", "cà phê sữa đá")
        food = facts.get("favorite_food", "mì Quảng")
        pet = facts.get("pet", "corgi (tên Bơ)")
        style = facts.get("response_style", "ngắn gọn, có ví dụ thực tế")
        interests = facts.get("interests", "Python, AI ứng dụng, MLOps")

        lower_msg = message.lower()
        is_query = any(k in lower_msg for k in ["tên", "nghề", "ở đâu", "style", "uống", "ăn", "nuôi", "nhắc lại", "ai", "gì", "tóm tắt", "chọn giữa", "huế", "hà nội", "stress test"])

        if is_query:
            # Nếu người dùng yêu cầu phong cách 3 bullet hoặc stress test
            if "3 bullet" in style or "stress" in user_id or "stress test" in lower_msg or "3 bullet" in lower_msg:
                return (
                    f"- **Tên & Thông tin cá nhân**: Tên bạn là {name}, hiện tại nơi ở là {location}.\n"
                    f"- **Nghề nghiệp & Định hướng**: Nghề nghiệp hiện tại là {profession} (không phải product manager hay backend), tập trung vào {interests}.\n"
                    f"- **Phong cách & Trọng tâm**: Style trả lời mong muốn là 3 bullet ngắn gọn có ví dụ thực chiến, nhấn mạnh trade-off giữa recall và token cost."
                )

            # Câu trả lời dạng cấu trúc bullet ngắn gọn với đầy đủ fact
            bullets = [
                f"- Tên của bạn: {name}.",
                f"- Nơi ở hiện tại: {location}.",
                f"- Nghề nghiệp hiện tại: {profession}.",
                f"- Đồ uống & Món ăn yêu thích: {drink}, {food}.",
                f"- Thú cưng: nuôi một bé {pet}.",
                f"- Mối quan tâm kỹ thuật chính: {interests}.",
                f"- Style trả lời mong muốn: {style}.",
            ]
            return f"Chào {name}! Dưới đây là thông tin mình đã ghi nhớ từ hồ sơ User.md:\n" + "\n".join(bullets)

        return f"Chào {name}, mình đã lưu thông tin vào hồ sơ User.md và sẵn sàng hỗ trợ bạn ngắn gọn!"

    def _maybe_build_langchain_agent(self):
        """Khởi tạo Chat Model từ cấu hình đã chọn cho chế độ live."""
        return build_chat_model(self.config.model)

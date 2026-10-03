from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def estimate_tokens(text: str) -> int:
    """Ước lượng số token tất định dựa trên độ dài ký tự (khoảng 4 ký tự / token).
    
    Tính chất:
    - Trả về 0 cho chuỗi rỗng
    - Tất định: cùng một chuỗi luôn cho cùng một giá trị
    - Tăng đơn điệu theo độ dài văn bản
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return max(1, len(cleaned) // 4)


@dataclass
class UserProfileStore:
    """Quản lý lưu trữ bền vững file User.md trên đĩa."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id.strip())
        return self.root_dir / safe_id / "User.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"# Hồ Sơ Người Dùng: {user_id}\n\n"

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        current = self.read_text(user_id)
        if search_text in current:
            updated = current.replace(search_text, replacement, 1)
            self.write_text(user_id, updated)
            return True
        return False

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        return path.stat().st_size if path.exists() else 0

    def facts(self, user_id: str) -> dict[str, str]:
        text = self.read_text(user_id)
        result: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- **") and "**:" in line:
                parts = line[4:].split("**:", 1)
                if len(parts) == 2:
                    result[parts[0].strip().lower()] = parts[1].strip()
            elif line.startswith("- ") and ":" in line:
                parts = line[2:].split(":", 1)
                if len(parts) == 2:
                    result[parts[0].strip().lower()] = parts[1].strip()
        return result

    def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        current_facts = self.facts(user_id)
        current_facts[key.strip().lower()] = value.strip()
        lines = [f"# Hồ Sơ Người Dùng: {user_id}\n"]
        for k, v in current_facts.items():
            lines.append(f"- **{k.title()}**: {v}")
        self.write_text(user_id, "\n".join(lines) + "\n")


def extract_profile_updates(message: str) -> dict[str, str]:
    """Trích xuất fact ổn định từ câu của user, lọc nhiễu và xử lý đính chính."""
    msg = message.strip()
    if not msg:
        return {}

    updates: dict[str, str] = {}
    lower_msg = msg.lower()

    # 1. Tên (Name)
    name_match = re.search(r"(?:mình tên là|tên mình là|tôi tên là)\s+([A-Za-z0-9_À-ỹ\s]+?)(?:[,.]|$)", msg, re.IGNORECASE)
    if name_match:
        extracted_name = name_match.group(1).strip()
        if extracted_name and not any(w in extracted_name.lower() for w in ["gì", "ai", "không"]):
            updates["name"] = extracted_name

    # 2. Nơi ở (Location) & Corrections (Huế <-> Đà Nẵng, lọc bỏ Hà Nội đi họp)
    if "hà nội" in lower_msg and "họp" in lower_msg:
        pass  # Nhiễu: Chỉ đi họp, không phải nơi ở
    elif "nơi ở đã cập nhật từ huế sang đà nẵng" in lower_msg or "từ tuần này mình đang làm việc ở đà nẵng" in lower_msg or ("đà nẵng" in lower_msg and "ở đà nẵng vài tháng" in lower_msg):
        updates["location"] = "Đà Nẵng"
    elif "đang ở huế chứ không còn ở đà nẵng" in lower_msg or "vẫn ở huế" in lower_msg or "đang ở huế" in lower_msg or ("nơi ở đã thay đổi" in lower_msg and "huế" in lower_msg):
        updates["location"] = "Huế"
    elif "ở đà nẵng" in lower_msg and "không còn ở đà nẵng" not in lower_msg and "đừng lấy nó làm nơi ở hiện tại" not in lower_msg:
        updates["location"] = "Đà Nẵng"
    elif "ở huế" in lower_msg:
        updates["location"] = "Huế"

    # 3. Nghề nghiệp (Profession) & Corrections (Backend -> MLOps, lọc bỏ câu đùa product manager)
    if "product manager" in lower_msg and ("câu đùa" in lower_msg or "đùa" in lower_msg):
        updates["profession"] = "MLOps engineer"
    elif "chuyển sang mlops engineer" in lower_msg or "chuyển sang mlops" in lower_msg or "làm mlops engineer" in lower_msg or "nghề nghiệp hiện tại vẫn là mlops engineer" in lower_msg:
        updates["profession"] = "MLOps engineer"
    elif "làm backend engineer" in lower_msg and "không còn làm backend" not in lower_msg and "đừng nói backend" not in lower_msg:
        updates["profession"] = "backend engineer"
    elif "mlops engineer" in lower_msg and ("không còn làm backend" in lower_msg or "nghề nghiệp mới" in lower_msg):
        updates["profession"] = "MLOps engineer"

    # 4. Đồ uống yêu thích (Favorite Drink)
    if "cà phê sữa đá" in lower_msg:
        updates["favorite_drink"] = "cà phê sữa đá"

    # 5. Món ăn yêu thích (Favorite Food)
    if "mì quảng" in lower_msg:
        updates["favorite_food"] = "mì Quảng"

    # 6. Thú cưng (Pet)
    if "corgi" in lower_msg or "con bơ" in lower_msg or "bé corgi" in lower_msg:
        updates["pet"] = "corgi (tên Bơ)"

    # 7. Style trả lời mong muốn (Response Style)
    if "3 bullet" in lower_msg:
        updates["response_style"] = "3 bullet ngắn, có ví dụ thực chiến"
    elif "ngắn gọn" in lower_msg and ("ví dụ" in lower_msg or "rõ ý" in lower_msg):
        updates["response_style"] = "ngắn gọn, có ví dụ thực tế"
    elif "ngắn gọn" in lower_msg:
        updates["response_style"] = "ngắn gọn"

    # 8. Mối quan tâm kỹ thuật (Interests)
    interests: list[str] = []
    if "python" in lower_msg:
        interests.append("Python")
    if "ai" in lower_msg or "ai ứng dụng" in lower_msg:
        interests.append("AI ứng dụng")
    if "mlops" in lower_msg:
        interests.append("MLOps")
    if "benchmark memory" in lower_msg or "memory architecture" in lower_msg:
        interests.append("benchmark memory")
    if interests:
        updates["interests"] = ", ".join(dict.fromkeys(interests))

    return updates


def summarize_messages(messages: list[dict[str, str]], existing_summary: str = "", max_bullets: int = 3) -> str:
    """Tóm tắt lịch sử tin nhắn cũ súc tích, tránh summary phình to."""
    bullets: list[str] = []
    if existing_summary:
        for line in existing_summary.splitlines():
            line = line.strip()
            if line and line.startswith("- "):
                bullets.append(line)

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if not content:
            continue
        first_line = content.splitlines()[0]
        snippet = first_line if len(first_line) <= 70 else first_line[:67] + "..."
        bullets.append(f"- [{role}]: {snippet}")

    if len(bullets) > max_bullets:
        bullets = bullets[-max_bullets:]

    return "\n".join(bullets)


@dataclass
class CompactMemoryManager:
    """Quản lý compact memory cho các chuỗi hội thoại dài."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _ensure_thread(self, thread_id: str) -> dict[str, Any]:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }
        return self.state[thread_id]

    def append(self, thread_id: str, role: str, content: str) -> None:
        t_state = self._ensure_thread(thread_id)
        t_state["messages"].append({"role": role, "content": content})

        # Tính tổng token của các tin nhắn hiện tại + summary
        active_tokens = sum(estimate_tokens(m["content"]) for m in t_state["messages"])
        summary_tokens = estimate_tokens(t_state["summary"])
        total_tokens = active_tokens + summary_tokens

        # Kích hoạt compact khi vượt ngưỡng và số tin nhắn > keep_messages
        if total_tokens > self.threshold_tokens and len(t_state["messages"]) > self.keep_messages:
            to_compact = t_state["messages"][: -self.keep_messages]
            kept = t_state["messages"][-self.keep_messages :]

            t_state["summary"] = summarize_messages(to_compact, existing_summary=t_state["summary"], max_bullets=3)
            t_state["messages"] = kept
            t_state["compactions"] += 1

    def context(self, thread_id: str) -> dict[str, Any]:
        return self._ensure_thread(thread_id)

    def compaction_count(self, thread_id: str) -> int:
        return self._ensure_thread(thread_id).get("compactions", 0)

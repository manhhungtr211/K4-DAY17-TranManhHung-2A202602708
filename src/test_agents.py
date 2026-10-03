from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated config for tests."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = state_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    dummy_model = ProviderConfig(provider="openai", model_name="gpt-4o-mini", temperature=0.0)

    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=state_dir,
        compact_threshold_tokens=50,  # Ngưỡng thấp để compact kích hoạt nhanh trong test
        compact_keep_messages=2,
        model=dummy_model,
        judge_model=dummy_model,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, updated, and edited."""
    profiles_dir = tmp_path / "state" / "profiles"
    store = UserProfileStore(profiles_dir)

    user_id = "dungct_test"
    # 1. Ghi hồ sơ mới
    initial_content = "# Hồ Sơ Người Dùng: dungct_test\n\n- **Name**: DũngCT\n- **Location**: Đà Nẵng\n"
    path = store.write_text(user_id, initial_content)
    assert path.exists(), "File User.md phải tồn tại trên đĩa"
    assert store.file_size(user_id) > 0, "Dung lượng file phải lớn hơn 0"

    # 2. Đọc lại nội dung
    read_back = store.read_text(user_id)
    assert "DũngCT" in read_back
    assert "Đà Nẵng" in read_back

    # 3. Sửa thông tin (Correction qua edit_text)
    changed = store.edit_text(user_id, "Đà Nẵng", "Huế")
    assert changed is True, "edit_text phải trả về True khi thay thế thành công"
    updated_content = store.read_text(user_id)
    assert "Huế" in updated_content
    assert "Đà Nẵng" not in updated_content

    # 4. Upsert fact
    store.upsert_fact(user_id, "profession", "MLOps engineer")
    facts = store.facts(user_id)
    assert facts.get("profession") == "MLOps engineer"


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction."""
    # Ngưỡng 30 tokens, giữ 2 messages gần nhất
    manager = CompactMemoryManager(threshold_tokens=30, keep_messages=2)
    thread_id = "thread_compact_test"

    # Bơm 6 tin nhắn dài vượt ngưỡng token
    for i in range(6):
        manager.append(
            thread_id,
            "user" if i % 2 == 0 else "assistant",
            f"Đây là thông điệp rất dài lượt thứ {i} để kiểm tra kích hoạt compact memory.",
        )

    compaction_count = manager.compaction_count(thread_id)
    assert compaction_count > 0, "Compaction phải được kích hoạt ít nhất 1 lần"

    ctx = manager.context(thread_id)
    assert len(ctx["messages"]) <= 3, "Chỉ được giữ lại tối đa số tin nhắn keep_messages"
    assert len(ctx["summary"]) > 0, "Summary phải chứa nội dung lịch sử đã được nén"


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced remembers across sessions and baseline does not."""
    config = make_config(tmp_path)

    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    user_id = "dungct_recall_test"

    # Phiên 1: Cung cấp fact tên và đồ uống cho cả 2 agent
    baseline.reply(user_id, "thread_1", "Chào bạn, mình tên là DũngCT và đồ uống yêu thích là cà phê sữa đá.")
    advanced.reply(user_id, "thread_1", "Chào bạn, mình tên là DũngCT và đồ uống yêu thích là cà phê sữa đá.")

    # Phiên 2: Hỏi lại ở thread hoàn toàn mới
    baseline_resp = baseline.reply(user_id, "thread_2", "Mình tên gì và đồ uống yêu thích của mình là gì?")
    advanced_resp = advanced.reply(user_id, "thread_2", "Mình tên gì và đồ uống yêu thích của mình là gì?")

    # Baseline bắt buộc KHÔNG ĐƯỢC nhớ ở thread mới
    assert (
        "dũngct" not in baseline_resp["content"].lower()
        or "cà phê sữa đá" not in baseline_resp["content"].lower()
    ), "Baseline không được nhớ fact qua thread mới"

    # Advanced bắt buộc PHẢI nhớ ở thread mới nhờ User.md
    assert "dũngct" in advanced_resp["content"].lower(), "Advanced phải nhớ tên người dùng ở thread mới"
    assert "cà phê sữa đá" in advanced_resp["content"].lower(), "Advanced phải nhớ đồ uống yêu thích ở thread mới"


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    config = make_config(tmp_path)
    config.compact_threshold_tokens = 50
    config.compact_keep_messages = 2

    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    user_id = "dungct_stress_test"
    thread_id = "long_thread_test"

    long_message = "Đây là đoạn văn bản dài chứa nhiều thông tin chi tiết về hệ thống MLOps và các pipeline AI phức tạp để tạo áp lực lớn lên số lượng prompt tokens processed qua từng lượt trò chuyện."

    for _ in range(10):
        baseline.reply(user_id, thread_id, long_message)
        advanced.reply(user_id, thread_id, long_message)

    baseline_prompt_tokens = baseline.prompt_token_usage(thread_id)
    advanced_prompt_tokens = advanced.prompt_token_usage(thread_id)

    assert advanced.compaction_count(thread_id) > 0, "Advanced agent phải có compaction"
    assert advanced_prompt_tokens < baseline_prompt_tokens, (
        f"Prompt tokens của Advanced ({advanced_prompt_tokens}) phải nhỏ hơn Baseline ({baseline_prompt_tokens})"
    )

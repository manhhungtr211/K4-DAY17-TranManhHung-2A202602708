from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Return 0, 0.5, or 1 depending on how many expected facts appear."""
    if not expected:
        return 1.0
    lower_ans = answer.lower()
    matches = sum(1 for exp in expected if exp.lower() in lower_ans)
    if matches == len(expected):
        return 1.0
    elif matches > 0:
        return 0.5
    else:
        return 0.0


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight quality score for offline mode."""
    rp = recall_points(answer, expected)
    length = len(answer.strip())
    length_score = 1.0 if 15 <= length <= 600 else 0.5
    structure_bonus = 0.1 if ("-" in answer or "\n" in answer or "*" in answer) else 0.0
    score = (rp * 0.75) + (length_score * 0.15) + structure_bonus
    return min(1.0, max(0.0, round(score, 2)))


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Evaluate one agent over a conversation suite."""
    total_agent_tokens = 0
    total_prompt_tokens = 0
    total_compactions = 0
    recall_scores: list[float] = []
    quality_scores: list[float] = []
    unique_users = set()

    for conv in conversations:
        user_id = conv["user_id"]
        unique_users.add(user_id)
        thread_id = conv["id"]

        # 1. Feed turns sequentially
        for turn in conv.get("turns", []):
            agent.reply(user_id, thread_id, turn)

        total_agent_tokens += agent.token_usage(thread_id)
        total_prompt_tokens += agent.prompt_token_usage(thread_id)
        total_compactions += agent.compaction_count(thread_id)

        # 2. Test cross-session recall in fresh thread
        for idx, q in enumerate(conv.get("recall_questions", [])):
            fresh_thread_id = f"{thread_id}-recall-{idx}"
            resp = agent.reply(user_id, fresh_thread_id, q["question"])
            ans_text = resp.get("content", "")
            expected = q.get("expected_contains", [])

            total_agent_tokens += resp.get("tokens", 0)
            total_prompt_tokens += resp.get("prompt_tokens", 0)

            rp = recall_points(ans_text, expected)
            hq = heuristic_quality(ans_text, expected)
            recall_scores.append(rp)
            quality_scores.append(hq)

    # 3. Measure total persistent memory growth
    memory_growth = 0
    if hasattr(agent, "memory_file_size"):
        for uid in unique_users:
            memory_growth += agent.memory_file_size(uid)

    avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=round(avg_recall, 3),
        response_quality=round(avg_quality, 3),
        memory_growth_bytes=memory_growth,
        compactions=total_compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows as a markdown table."""
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    table_data = [
        [
            r.agent_name,
            f"{r.agent_tokens_only:,}",
            f"{r.prompt_tokens_processed:,}",
            f"{r.recall_score * 100:.1f}%",
            f"{r.response_quality * 100:.1f}%",
            f"{r.memory_growth_bytes:,}",
            f"{r.compactions}",
        ]
        for r in rows
    ]
    try:
        from tabulate import tabulate

        return tabulate(table_data, headers=headers, tablefmt="github")
    except ImportError:
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        body_lines = [
            f"| {' | '.join(str(cell) for cell in row)} |"
            for row in table_data
        ]
        return "\n".join([header_line, sep_line] + body_lines)


def main() -> None:
    """Run both standard and long-context stress benchmark suites."""
    config = load_config(Path(__file__).resolve().parent.parent)

    std_data_path = config.data_dir / "conversations.json"
    stress_data_path = config.data_dir / "advanced_long_context.json"

    std_conversations = load_conversations(std_data_path)
    stress_conversations = load_conversations(stress_data_path)

    # 1. Standard Benchmark Suite
    print("STANDARD BENCHMARK (data/conversations.json - 10 Conversations)")

    # Reset state directory before benchmark run
    if config.state_dir.exists():
        shutil.rmtree(config.state_dir)
    config.state_dir.mkdir(parents=True, exist_ok=True)

    baseline_std = BaselineAgent(config, force_offline=True)
    row_baseline_std = run_agent_benchmark("Baseline Agent", baseline_std, std_conversations, config)

    advanced_std = AdvancedAgent(config, force_offline=True)
    row_advanced_std = run_agent_benchmark("Advanced Agent", advanced_std, std_conversations, config)

    print(format_rows([row_baseline_std, row_advanced_std]))
    print()

    # 2. Long-Context Stress Benchmark Suite
    print("LONG-CONTEXT STRESS BENCHMARK (data/advanced_long_context.json - 16 Turns Stress)")

    # Reset state directory before stress run
    if config.state_dir.exists():
        shutil.rmtree(config.state_dir)
    config.state_dir.mkdir(parents=True, exist_ok=True)

    baseline_stress = BaselineAgent(config, force_offline=True)
    row_baseline_stress = run_agent_benchmark("Baseline Agent", baseline_stress, stress_conversations, config)

    advanced_stress = AdvancedAgent(config, force_offline=True)
    row_advanced_stress = run_agent_benchmark("Advanced Agent", advanced_stress, stress_conversations, config)

    print(format_rows([row_baseline_stress, row_advanced_stress]))


if __name__ == "__main__":
    main()

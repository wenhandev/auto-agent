"""Run a harder end-to-end test: fetch Apple new-product prices from the official site."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = os.environ.get("AUTO_AGENT_PORT", "8001")
HOST = os.environ.get("AUTO_AGENT_HOST", "127.0.0.1")
WS = f"ws://{HOST}:{PORT}/ws/run"

WORKFLOW = {
    "nodes": [
        {
            "id": "n1",
            "type": "navigate",
            "label": "打开苹果中国官网",
            "params": {"url": "https://www.apple.com.cn/"},
        },
        {
            "id": "n2",
            "type": "wait",
            "label": "等待首页加载",
            "params": {"ms": 3000},
        },
        {
            "id": "n3",
            "type": "fuzzy_action",
            "label": "进入商店并浏览新品",
            "params": {
                "instruction": (
                    "当前在苹果中国官网。如有 cookie 或弹窗先关闭。"
                    "进入「商店」或「购买」相关页面，浏览 2025-2026 年发布的新品"
                    "（如 iPhone、Mac、iPad、Apple Watch 等最新款）。"
                    "必要时滚动或点击进入各产品线查看起售价。"
                    "在 done 的 summary 里列出你能找到的新品名称和人民币起售价。"
                )
            },
        },
        {
            "id": "n4",
            "type": "extract",
            "label": "整理价格清单",
            "params": {
                "instruction": (
                    "从当前页面提取 2025-2026 年苹果新品的名称和起售价格（人民币）。"
                    "以 JSON 数组输出，每项含 product 和 price 字段。"
                    "若页面信息不足，输出目前已知条目并注明缺失。"
                )
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4"},
    ],
    "start_id": "n1",
}


async def run() -> int:
    print("=== Apple 新品价格抓取测试 ===\n")
    node_results: dict[str, object] = {}
    run_ok = False
    run_error: str | None = None

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "workflow": WORKFLOW}))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                ev = msg.get("event")
                nid = msg.get("node_id")

                if ev == "node_started":
                    print(f"[started ] {nid}")
                elif ev == "node_progress":
                    print(f"[progress] {nid}: {msg.get('message')}")
                elif ev == "node_completed":
                    result = msg.get("output")
                    node_results[nid] = result
                    print(f"[done    ] {nid}")
                    if result is not None:
                        print(f"           output: {json.dumps(result, ensure_ascii=False)[:800]}")
                elif ev == "node_failed":
                    print(f"[FAILED  ] {nid}: {msg.get('error')}")
                    run_error = msg.get("error")
                elif ev == "run_completed":
                    run_ok = True
                    print("\n[run     ] completed")
                elif ev == "run_failed":
                    run_error = msg.get("error")
                    print(f"\n[run     ] failed: {run_error}")
                elif ev == "run_started":
                    print("[run     ] started\n")
        except websockets.ConnectionClosed:
            pass

    print("\n=== 最终结果 ===")
    fuzzy = node_results.get("n3")
    extract = node_results.get("n4")
    if isinstance(fuzzy, dict) and fuzzy.get("summary"):
        print("【Fuzzy 浏览摘要】")
        print(fuzzy["summary"])
        print()
    if isinstance(extract, dict) and extract.get("text"):
        print("【Extract 价格清单】")
        print(extract["text"])
    elif run_error:
        print(f"失败: {run_error}")
    else:
        print("原始输出:", json.dumps(node_results, ensure_ascii=False, indent=2))

    return 0 if run_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))

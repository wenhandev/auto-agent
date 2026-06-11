from __future__ import annotations

from app.schemas import Edge, Node, Workflow


SAMPLE_WORKFLOW: Workflow = Workflow(
    nodes=[
        Node(id="n1", type="navigate", label="打开示例页面",
             params={"url": "https://example.com"}),
        Node(id="n2", type="wait", label="等待页面加载",
             params={"ms": 500}),
        Node(id="n3", type="fuzzy_action", label="分析页面找到主标题",
             params={"instruction": "找到 h1 主标题文字"}),
        Node(id="n4", type="extract", label="提取页面标题",
             params={"instruction": "返回 h1 的文字"}),
        Node(id="n5", type="navigate", label="跳转到 example.org",
             params={"url": "https://example.org"}),
        Node(id="n6", type="wait", label="等待 1 秒",
             params={"ms": 1000}),
    ],
    edges=[
        Edge(id="e1", source="n1", target="n2"),
        Edge(id="e2", source="n2", target="n3"),
        Edge(id="e3", source="n3", target="n4"),
        Edge(id="e4", source="n4", target="n5"),
        Edge(id="e5", source="n5", target="n6"),
    ],
    start_id="n1",
)

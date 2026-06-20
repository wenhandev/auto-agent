from __future__ import annotations

from app.schemas import Edge, Node, Workflow

APPLE_NEW_PRODUCTS_WORKFLOW: Workflow = Workflow(
    nodes=[
        Node(
            id="n1",
            type="navigate",
            label="打开 iPhone 购买页",
            params={"url": "https://www.apple.com.cn/shop/buy-iphone"},
        ),
        Node(
            id="n2",
            type="wait",
            label="等待 iPhone 页面加载",
            params={"ms": 3000},
        ),
        Node(
            id="n3",
            type="extract",
            label="提取 iPhone 新品价格",
            params={
                "instruction": (
                    "列出页面上所有 iPhone 型号及其人民币起售价格。"
                    "JSON 数组，每项含 product 和 price 字段。"
                )
            },
        ),
        Node(
            id="n4",
            type="navigate",
            label="打开 Mac 购买页",
            params={"url": "https://www.apple.com.cn/shop/buy-mac/macbook-pro"},
        ),
        Node(
            id="n5",
            type="wait",
            label="等待 Mac 页面加载",
            params={"ms": 3000},
        ),
        Node(
            id="n6",
            type="extract",
            label="提取 Mac 新品价格",
            params={
                "instruction": (
                    "列出页面上 Mac 各型号及其人民币起售价格。"
                    "JSON 数组，每项含 product 和 price 字段。"
                )
            },
        ),
        Node(
            id="n7",
            type="navigate",
            label="打开 iPad 购买页",
            params={"url": "https://www.apple.com.cn/shop/buy-ipad/ipad-pro"},
        ),
        Node(
            id="n8",
            type="wait",
            label="等待 iPad 页面加载",
            params={"ms": 3000},
        ),
        Node(
            id="n9",
            type="extract",
            label="提取 iPad 新品价格",
            params={
                "instruction": (
                    "列出页面上 iPad 各型号及其人民币起售价格。"
                    "JSON 数组，每项含 product 和 price 字段。"
                )
            },
        ),
        Node(
            id="n10",
            type="navigate",
            label="打开 Apple Watch 购买页",
            params={"url": "https://www.apple.com.cn/shop/buy-watch/apple-watch"},
        ),
        Node(
            id="n11",
            type="wait",
            label="等待 Watch 页面加载",
            params={"ms": 3000},
        ),
        Node(
            id="n12",
            type="extract",
            label="提取 Apple Watch 新品价格",
            params={
                "instruction": (
                    "列出页面上 Apple Watch 各型号及其人民币起售价格。"
                    "JSON 数组，每项含 product 和 price 字段。"
                )
            },
        ),
    ],
    edges=[
        Edge(id="e1", source="n1", target="n2"),
        Edge(id="e2", source="n2", target="n3"),
        Edge(id="e3", source="n3", target="n4"),
        Edge(id="e4", source="n4", target="n5"),
        Edge(id="e5", source="n5", target="n6"),
        Edge(id="e6", source="n6", target="n7"),
        Edge(id="e7", source="n7", target="n8"),
        Edge(id="e8", source="n8", target="n9"),
        Edge(id="e9", source="n9", target="n10"),
        Edge(id="e10", source="n10", target="n11"),
        Edge(id="e11", source="n11", target="n12"),
    ],
    start_id="n1",
)

APPLE_WORKFLOW_NAME = "苹果新品价格采集"
APPLE_WORKFLOW_DESCRIPTION = (
    "依次访问苹果中国官网 iPhone / Mac / iPad / Apple Watch 购买页，"
    "用 LLM 提取各产品线 2025-2026 新品的人民币起售价格。"
)

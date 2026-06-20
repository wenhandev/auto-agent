"""Route skill runtime tests."""

from __future__ import annotations

import uuid

from sqlmodel import Session

from app.db.models import RouteSkill
from app.db.session import engine, init_db
from app.services import route_skills


def _unique_pattern(path: str) -> str:
    marker = uuid.uuid4().hex[:8]
    return f"https://example.com/{marker}{path}"


def test_route_skill_matches_normalized_url_and_ignores_disabled() -> None:
    init_db()
    pattern = _unique_pattern("/users/{id}")
    disabled_pattern = _unique_pattern("/disabled/{id}")
    with Session(engine) as session:
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=pattern,
                prompt="Use user admin flow",
                allowed_tools_json='["click_element","finish"]',
                priority=10,
                enabled=True,
            )
        )
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=disabled_pattern,
                prompt="Disabled",
                allowed_tools_json='["finish"]',
                priority=100,
                enabled=False,
            )
        )
        session.commit()

        matched = route_skills.match_route_skills(
            session,
            pattern.replace("{id}", "123") + "?utm_source=x",
        )
        disabled = route_skills.match_route_skills(
            session,
            disabled_pattern.replace("{id}", "123"),
        )

    assert [skill.prompt for skill in matched] == ["Use user admin flow"]
    assert disabled == []


def test_route_skill_priority_order_and_tool_intersection() -> None:
    init_db()
    pattern = _unique_pattern("/deploy")
    with Session(engine) as session:
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=pattern,
                prompt="Low priority",
                allowed_tools_json='["click_element","finish"]',
                priority=1,
                enabled=True,
            )
        )
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=pattern,
                prompt="High priority",
                allowed_tools_json='["finish","integration"]',
                priority=50,
                enabled=True,
            )
        )
        session.commit()

        context = route_skills.build_route_context(
            session,
            pattern,
            task_allowed_tools=frozenset({"click_element", "finish"}),
        )

    assert context.skill_ids
    assert context.prompts == ["High priority", "Low priority"]
    assert context.allowed_tools == frozenset({"finish"})


def test_route_skill_cannot_expand_task_allowed_tools() -> None:
    init_db()
    pattern = _unique_pattern("/billing")
    with Session(engine) as session:
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=pattern,
                prompt="Billing",
                allowed_tools_json='["finish","integration"]',
                priority=1,
                enabled=True,
            )
        )
        session.commit()

        context = route_skills.build_route_context(
            session,
            pattern,
            task_allowed_tools=frozenset({"finish"}),
        )

    assert context.allowed_tools == frozenset({"finish"})


def test_route_skills_api_smoke(client) -> None:
    pattern = _unique_pattern("/api-smoke")
    create = client.post(
        "/api/route-skills",
        json={
            "url_pattern": pattern,
            "prompt": "Smoke test route skill",
            "allowed_tools": ["finish"],
            "priority": 5,
        },
    )
    assert create.status_code == 200, create.text
    skill_id = create.json()["id"]
    listed = client.get("/api/route-skills")
    assert listed.status_code == 200
    assert any(row["id"] == skill_id for row in listed.json())
    fetched = client.get(f"/api/route-skills/{skill_id}")
    assert fetched.status_code == 200
    assert fetched.json()["url_pattern"] == pattern
    deleted = client.delete(f"/api/route-skills/{skill_id}")
    assert deleted.status_code == 200

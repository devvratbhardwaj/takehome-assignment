import pytest

from app.agent import build_system_prompt, get_agent
from app.db import get_connection, init_schema


@pytest.fixture
def database_path(tmp_path, monkeypatch):
    path = tmp_path / "agent.db"
    monkeypatch.setenv("INVENTORY_DB", str(path))
    connection = get_connection(path)
    init_schema(connection)
    connection.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("as_of_date", "2026-08-01"), ("currency", "CAD")],
    )
    connection.commit()
    connection.close()
    return path


def test_system_prompt_cites_meta(database_path):
    prompt = build_system_prompt()
    assert "2026-08-01" in prompt
    assert "CAD" in prompt


def test_agent_constructs_with_bound_tools(database_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_agent.cache_clear()
    try:
        agent = get_agent()
        assert get_agent() is agent
        node_names = set(agent.get_graph().nodes)
        assert "tools" in node_names
    finally:
        get_agent.cache_clear()

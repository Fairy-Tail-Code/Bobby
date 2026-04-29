from pathlib import Path

from agents.prompts.loader import load_prompt
from infrastructure.paths import ensure_agent_prompts, get_agent_prompts_dir


def test_load_prompt_exists():
    planner = load_prompt("planner")
    assert "Planner" in planner
    assert len(planner) > 100


def test_load_all_prompts():
    for name in ["pm", "planner", "generator", "evaluator"]:
        prompt = load_prompt(name)
        assert len(prompt) > 100, f"Prompt for {name} is too short"


def test_prompts_dir_is_under_home():
    prompts_dir = get_agent_prompts_dir()
    assert ".openharness" in str(prompts_dir)
    assert "agents" in str(prompts_dir) and "prompts" in str(prompts_dir)


def test_ensure_agent_prompts_copies_files(tmp_path, monkeypatch):
    """ensure_agent_prompts copies .md files from bundled dir to home dir."""
    monkeypatch.setenv("OPENHARNESS_HOME", str(tmp_path))

    src_dir = tmp_path / "src" / "agents" / "prompts"
    src_dir.mkdir(parents=True)
    (src_dir / "test_agent.md").write_text("Hello test agent", encoding="utf-8")

    import infrastructure.paths as paths

    monkeypatch.setattr(paths, "get_home", lambda: tmp_path)
    monkeypatch.setattr(paths, "_get_bundled_prompts_dir", lambda: src_dir)

    ensure_agent_prompts()

    copied = tmp_path / "agents" / "prompts" / "test_agent.md"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "Hello test agent"

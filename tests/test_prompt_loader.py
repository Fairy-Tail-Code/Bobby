from agents.prompts.loader import load_prompt


def test_load_prompt_exists():
    planner = load_prompt("planner")
    assert "Planner" in planner
    assert len(planner) > 100


def test_load_all_prompts():
    for name in ["planner", "generator", "evaluator"]:
        prompt = load_prompt(name)
        assert len(prompt) > 100, f"Prompt for {name} is too short"
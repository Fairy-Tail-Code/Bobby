from autogen import ConversableAgent

from infrastructure.skills import SkillRegistry


def inject_skill_summaries(
    agent: ConversableAgent,
    skill_names: list[str],
    skill_registry: SkillRegistry,
) -> None:
    """Inject compact skill summaries into agent system message (progressive disclosure layer 1)."""
    summary_block = skill_registry.build_summary_block(skill_names)
    if summary_block:
        original = agent.system_message
        agent.update_system_message(original + "\n\n" + summary_block)

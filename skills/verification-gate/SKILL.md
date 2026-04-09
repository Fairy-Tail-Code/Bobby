---
name: verification-gate
description: Return structured verification gate results for the current delivery iteration.
---

# Verification Gate

Produce the structured verification result for the current delivery iteration.

Execution rules:
- Read the runtime inference payload and the observed verification context first.
- Focus on whether the required language-native verification commands actually succeeded for each relevant subsystem.
- Return JSON only that matches the required output schema.
- Do not modify the repository.

Return:
- status
- language
- topology
- required_commands
- observed_successful_commands
- missing_required_commands
- subsystems
- quality_gates
- summary
- notes

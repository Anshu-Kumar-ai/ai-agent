# Skill Update: hermes-agent

## Summary of Changes

Updated the hermes-agent skill to include documentation about extension contracts for Stage 32 Phase 1:

1. **Added new reference file**: `references/extension-contracts.md`
   - Contains detailed contracts for extending Hermes Agent:
     - Provider Interface (LLM providers)
     - Tool Interface & Metadata (tools)
     - Skill Contract (skills/workflows)
     - Application Adapter Contract
     - Registration Model
     - Security Requirements
     - Backward Compatibility Strategy
     - Examples for adding new tools and skills

2. **Updated skill routing table**:
   - Added entry for extending Hermes with provider, tool, skill, and adapter contracts
   - Points to the new `references/extension-contracts.md` file

## Purpose

This update captures the learning from implementing Stage 32 Phase 1 extension contracts work, making this knowledge available for future sessions. When users ask about extending Hermes Agent with new LLM providers, tools, skills, or application adapters, the agent will now know to load the extension-contracts.md reference to provide accurate, detailed information.

The update follows the skill library guidelines:
- Procedure-first documentation with concrete examples
- Generalizable rules (not session-specific narratives)
- Always-on rules in SKILL.md (the routing table update)
- Topical depth in references/ (the extension-contracts.md file)
- No environment-dependent failures or negative tool claims
- No unresolved failure narratives

## Verification

The hermes-agent skill was successfully updated and can now route questions about extension contracts to the appropriate reference file. The new reference file contains comprehensive, accurate information about the extension contracts implemented during this session.
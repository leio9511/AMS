status: in_progress

# PR-001: Update AMS AgentSkill for Native Announce Delivery

## 1. Objective
Sync the AMS AgentSkill prompt configuration to use OpenClaw's modern native announce delivery mechanism, removing all deprecated message tool references.

## 2. Scope (Functional & Implementation Freedom)
- Locate the LLM system prompt definition for the AMS project.
- Remove all instructions, references, and examples related to the deprecated `message` tool.
- Integrate explicit instructions and logic for using the native `announce` delivery mechanism.
- Ensure the prompt structure remains intact and valid according to the AgentSkill specification.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- The AMS AgentSkill configuration file no longer contains instructions to use the `message` tool.
- Explicit instructions for native `announce` delivery are present in the configuration.
- The modified configuration successfully validates against the latest OpenClaw AgentSkill specification.
- The Coder MUST ensure all tests run GREEN before submitting.
---
description: Turn a warehouse request into a design-first Isaac Sim scenario, then Python, then GUI fallback if needed
argument-hint: [plain-english warehouse scenario]
---

Use the isaac-sim-warehouse-scenarios subagent for this task.

Request:
$ARGUMENTS

Required workflow:
1. Search this project for similar Isaac Sim samples before generating new code.
2. Produce a scenario spec first.
3. Then produce a Python implementation plan and code.
4. Add Behavior Tree or OmniGraph guidance only when needed.
5. Add Isaac Sim GUI fallback steps only if Python API support is missing, awkward, or unclear.
6. End with a validation checklist.

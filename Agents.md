
# Agent Instructions

## Guidelines
Before making any changes:
- Read docs/ProductRequirements.md in full
- Review any relevant files in docs/ related to the area being modified

## Change Rules
- Do not violate goals or non-goals defined in Design.md
- Preserve public APIs unless explicitly instructed
- Keep changes scoped to the requested area
- Do not introduce insecure storage or auth behavior
- Do not silently downgrade security or provider guarantees
- Keep a changelog.md. For each update action, add a corresponding line to the changelog.

## Documentation
- Update docs/ when behavior changes
- Do not modify ProductRequirements.md unless explicitly instructed
- Add changes to changelog.md

## Uncertainty
- If a change conflicts with Design.md, stop and ask

## Raw Input files
- This project relies on user supplied input files
- These files must never be moved, altered, or overwritten under any circumstances.
- See docs/RawInputs.md for details on these files.
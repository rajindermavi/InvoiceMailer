# Code Review Charter – Inventory Compliance Reporter

This review evaluates whether the code adheres to the intended architecture
and enforces proper contracts between layers.

The reviewer must NOT propose new features or refactors unless a contract
violation exists.

Primary evaluation dimensions:

1. Contract enforcement
   - Are function inputs validated at the correct layer?
   - Are return types explicit and reliable?
   - Are error states represented or silently ignored?

2. Layering discipline
   - Frontend orchestrates only; no domain logic
   - Domain logic has no I/O, no persistence
   - Storage layer has no business rules

3. Failure semantics
   - Can each module fail in a controlled, inspectable way?
   - Are errors propagated or swallowed?

4. Coupling & leakage
   - Are modules depending on concrete implementations unnecessarily?
   - Are configuration details leaking into domain logic?

5. Testability
   - Can core logic be tested without filesystem, Excel, or SQLite?
   - Are contracts testable independently?

Output must be findings only:
- Observations
- Violations
- Risk assessment
No code generation unless explicitly requested.

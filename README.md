# SigScout

[English](README.md) · [中文](README.zh.md)

> **signal-peptide discovery, screening, clustering, and experiment-guided exploration for secretion constructs.** It is built for reviewable decisions, not unqualified claims.

## Why it matters

This project makes a high-stakes research or product decision inspectable: inputs, constraints, evidence, and the final human decision remain visible.

## What makes it strong

> **Project-specific spotlight:** Source evidence, target-isolated feedback, and diversity stay separate instead of becoming one misleading score.

| Design choice | Value for an interviewer |
| --- | --- |
| Evidence before recommendation | Results retain source, constraint, and failure context |
| Human decision boundary | The system narrows choices; it does not authorize scientific, compliance, or deployment action |
| Explicit non-goals | Unsupported claims are documented rather than implied by a polished UI |
| Canon + tests | Requirements, architecture, status, handoff, and long-lived decisions remain separately reviewable |

## Workflow

```mermaid
flowchart LR
  A[Input or source data] --> B[Domain workflow]
  B --> C[Constraints and evidence]
  C --> D[Human review]
  D --> E[Traceable output]
```

## Architecture boundary

```mermaid
flowchart TB
  UI[User or API entry] --> APP[Application workflow]
  APP --> DOMAIN[Domain rules]
  APP --> PORTS[External-service boundary]
  DOMAIN --> OUT[Reviewable result]
  OUT --> HUMAN[Human decision]
```

## Quick start

Prepare the supported local environment, then run:

```powershell
python -m streamlit run src/sigscout/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8506
```

## Engineering evidence

| Checkpoint | Evidence | Boundary |
| --- | --- | --- |
| Product behavior | Run the focused tests named in Handoff | No output becomes a validated real-world outcome automatically |
| Documentation | Run the repository documentation guard | Current status belongs to the execution plan, not this README |
| Current direction | Read the execution plan before extending scope | No product slice is authorized; new sources or targets require explicit data and acceptance boundaries. |

## Authoritative project documents

| Document | Use it for |
| --- | --- |
| [Requirements](docs/REQUIREMENTS.md) | Scope and capability boundary |
| [Architecture](docs/ARCHITECTURE.md) | Layer rules and protected boundaries |
| [Execution plan](docs/EXECUTION_PLAN.md) | Current authority, gates, and blockers |
| [Handoff](docs/HANDOFF.md) | Current slice and verification |
| [ADR index](docs/adr/README.md) | Long-lived decisions and alternatives |

<details>
<summary>Technical interview lens</summary>

The strongest discussion point is not a framework name: it is the explicit boundary between evidence, computation, and the person who remains accountable for the final decision. Current status and blockers are intentionally linked rather than copied here.
</details>

> **Reflection:** Reliable tools do not hide uncertainty; they make the next decision easier to defend. Explore more work at [my personal site](https://77652189.github.io).

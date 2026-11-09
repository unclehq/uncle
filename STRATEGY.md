# Uncle — Positioning & Growth Strategy

Saved from Claude Code session so you can resume work in a fresh instance.

## The core problem

"Agentic workflow" was a generic, overused term. Without qualification, people
assumed this was yet another LangChain / LangGraph / AutoGPT-style
orchestration framework. The unique parts were buried in the description.

## What is actually uncommon here

Most agent tools optimize to remove humans. This project does the opposite:

- Human approval gates at every stage.
- Adversarial review by a second model (Claude builds, Codex audits).
- SHA-256 pinned specs so approved artifacts cannot be silently modified.
- Immutable reviewer-owned files that the implementing agent cannot edit.
- Speculative execution that is only adopted if the spec remains byte-identical.

That is not a generic agent framework. It is a **governance / adversarial CI layer** for AI-generated code.

## Positioning pivot

Frame it as the safety layer, not the agent itself:

> "Everyone else is building agents that run unsupervised. This is the approval layer that makes them acceptable in production."

Better descriptions:
- A governed CI pipeline for coding agents.
- Human-in-the-loop adversarial review for AI code.
- The approval layer between agents and production.
- Signed, auditable agent execution.

## Name

Chosen name: **`stagegate`** (`github.com/stagegate/stagegate`).

Alternatives considered:

- `agent-gate` — strongest fit, but unavailable
- `agent-checkpoint` — clear, but longer
- `vetting` — literal, but sounds like an activity, not a product
- `agent-signoff` — explicit, but corporate
- `agent-oversight` — governance angle, but dry

## How to get contributors

1. Make the first contribution trivial: label `good first issue`, write `CONTRIBUTING.md`, keep a public TODO board.
2. Write issues like invitations: include files to touch, tests to add, and estimated effort.
3. Show internals publicly: essays on the state machine, SHA-256 pinning, and speculative execution.
4. Recruit directly from adjacent projects (vLLM, Pydantic AI) after good interactions.
5. Be a fast, friendly maintainer for the first 30 days.
6. Offer weekly 30-minute "contributor office hours."

## Advertising / notoriety plan

1. Own one clear position and repeat it everywhere.
2. Launch with a story, not just a repo. Good angles:
   - "I let an autonomous agent run for a weekend and it silently broke my code."
   - "Why AI-generated code needs the same approval workflow as production deploys."
3. Write 3–4 authoritative essays:
   - "The Three-Gate Model for Safe Agentic Coding"
   - "Why Adversarial Review Beats Self-Correction in LLMs"
   - "SHA-256 Spec Pinning: A Cheap Trick That Prevents Agent Sabotage"
4. Post on Hacker News, Reddit (r/LocalLLaMA, r/MachineLearning, r/programming), Twitter/X, LinkedIn.
5. Borrow audiences: pitch talks, podcasts, newsletters, and guest posts.
6. Build a shareable demo that solves a real problem with a full audit trail.
7. Stack social proof early: user quotes, GitHub stars, case studies.
8. Turn your personal brand (`brian.biz`) into distribution — add a blog/writing section and link to the project prominently.

## Immediate next steps

- [x] Decide whether to keep the name "Agentic Workflow" or rebrand around governance/audit.
      Chosen: `stagegate`.
- [ ] Rewrite the README to lead with the safety/adversarial angle, not the generic term.
- [ ] Add `CONTRIBUTING.md`, `LICENSE`, and `good first issue` labels.
- [ ] Create a Docker one-liner or `docker compose up` demo.
- [ ] Record a 90-second demo video or GIF.
- [ ] Draft the HN launch post: "Why I will not let an agent commit to main."
- [ ] Enable GitHub Discussions.

## Related project recommendations

If you want to contribute elsewhere while building this, the best fits are:

- **LiteLLM** — provider/routing correctness, directly adjacent to your vLLM/Pydantic AI work.
- **DoWhy / EconML** — causal inference, matches your research profile.
- **llama.cpp** — if you want deeper inference-engine work in C/C++.

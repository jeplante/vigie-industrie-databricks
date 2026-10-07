# Repository agent instructions

## Permanent repository rules

- Read `docs/superpowers/specs/2026-09-29-current-state-baseline-design.md` before architectural work. Treat it as a working-tree snapshot, not proof of production state; use current code and executable configuration as authority.
- Preserve existing uncommitted work. Do not reset, clean, overwrite, or include unrelated changes in a commit or pull request.
- Use Python 3.12. Preserve published table contracts, read-only serving, P&C isolation, the P&C evidence checks (automatic review in `pnc_auto_review.py` since 2026-10-07, by decision of the user; a hand-written record in `config/pnc/reviewed_evidence.yaml` remains possible for an exception), and explicit missing-value behavior.
- Run the documented local pytest gate for code changes. Keep Databricks Connect, runtime, deployment, and live-workspace validation separate; run the relevant remote gate for Spark, Delta, deployment, or App integration changes when access is available, and report any gate that could not run.
- Do not claim Live Finance publication is cross-table atomic.
- Do not change schedules, deployments, published data, or live resources unless the task explicitly authorizes that specific action.

## Execution preference

- Use the applicable Superpowers skills without copying their procedures into this file.
- Once a user authorizes a bounded slice, carry it through implementation, relevant tests, verification, review, and a reviewable handoff in one sustained run. Resolve routine choices from the repository, task constraints, and evidence; do not pause at each skill or task boundary.
- For an end-to-end request, present the design, acceptance criteria, and plan before coding when applicable, then continue without a separate approval for each phase if they stay within the authorized scope. An explicit request to review or stop at a phase remains a stop point.
- Stop for a decision only when the user must choose a material scope or behavior tradeoff, approve an irreversible or security-sensitive external action not already authorized, or provide access that is unavailable. Complete independent work first and present the concrete result and remaining decision.
- The user has granted standing authorization to merge PRs created within an authorized task. Merge after required checks pass and review findings are resolved; do not pause solely for merge approval. Honor explicit review or stop points and repository branch protections.
- Honor explicit stop points such as "plan only" or "stop before implementation." Keep each slice within its agreed scope.

## Agent and model routing

- Delegate only when the task or an applicable workflow calls for independent parallel work. Select the least expensive model that can reliably complete each subtask; do not inherit a more expensive parent model by default.

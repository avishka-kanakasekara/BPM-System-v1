# Responsible AI (human supervision)

BPMFlow AI uses LLMs as **assistants inside a deterministic control plane**. Business control is not delegated to a model.

## Principles in this codebase

1. **Agent 1 is evidence-backed.** Extraction is tied to documents and IR chunks. When evidence is insufficient, the pipeline abstains rather than inventing vendors, amounts, or approvals.
2. **Verified facts win.** Persisted ProcessContext, PO, and invoice rows override caller-supplied “expected” totals and LLM suggestions.
3. **Agent 4 state is deterministic.** `StateMachine` has an explicit transition table. No LLM chooses COMPLETED vs EXCEPTION.
4. **Agent 2 executes only authorized steps.** One allow-listed tool, one receipt. It cannot approve or flip process stage.
5. **Agent 3 allocates eligible directory resources** subject to SoD and budget rules. Rankings are advisory.
6. **TO-BE recommendations require human review.** They cannot remove mandatory approvals, bypass SoD, or activate WorkflowPlans.
7. **Humans approve and supervise.** Purchase execution after a required gate needs an approver/admin. Demo seeds are explicit and admin-controlled.

The system **does not** autonomously approve purchases, run an entire workflow in one Agent 2 call, or auto-optimize production processes.

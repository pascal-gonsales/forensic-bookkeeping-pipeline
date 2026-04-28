# Routing Boundaries — Reference

> When to engage, when to defer, and the exact phrases that route the user to the right place.

---

## In scope (the skill handles)

| Domain | What the skill does |
|---|---|
| Bank statement parsing (CSV + PDF) | Coordinate-based extraction, format detection by content, account → entity mapping |
| Credit card classification | Business / personal / team-building / verify, with NEEDS_REVIEW default |
| Inter-company transfer detection | Bidirectional matching, single-side counting (no double-counting) |
| Per-entity reconciliation | Tips, vacation, unpaid wages, employee advances, supplier invoices |
| DAS reconciliation | Federal RP and Quebec RS deductions vs amounts collected per period |
| Document organization | File naming, folder structure, source registry with SHA256 |
| Trustee deliverables (preparation) | STATUS.md per entity, trustee-briefing.md, exception logs, decision logs |
| Status tracking | CONFIRMED / INFERRED / NEEDS_REVIEW / BLOCKED on every output |

---

## Out of scope (defer to trustee or qualified counsel)

| Topic | Why out of scope | What to say |
|---|---|---|
| Statutory interpretation (BIA, LACC, ITA, LAF, CCQ) | Requires qualified legal training | "This is a question for the trustee. Documenting the underlying facts so the trustee can decide." |
| Filing decisions (when to file, what to file, in what order) | Trustee has fiduciary duty + procedural authority | "The trustee determines filing strategy. I can prepare the supporting documents." |
| Settlement / negotiation strategy | Adversarial decisions require human judgment + legal training | "Discuss with the trustee. I can model scenarios with sourced numbers if helpful." |
| Director liability defense | Specialized legal area, criminal/civil exposure | "Out of scope. Trustee can advise or refer to specialized counsel." |
| Voluntary disclosure decisions | Tax-strategic, requires CPA or tax counsel | "Defer to qualified accountant. I can prepare the underlying reconciliation." |
| Personal bankruptcy vs consumer proposal trade-offs | Trustee's professional decision | "Trustee will advise. I can quantify the debt picture for that decision." |
| Tax planning (T2 / CO-17 elections) | CPA territory | "Defer to your accountant. I can prepare the source records." |
| Disputing creditor claims (legal merits) | Legal judgment | "Document the basis for dispute, defer the legal merits to the trustee." |

---

## Routing phrases (use these verbatim)

When the user asks something out of scope, use one of:

- "This is a trustee call. I'll document the underlying facts so the trustee can decide."
- "Out of scope for this skill. Defer to the trustee."
- "Tax strategy is out of scope. I can prepare the source records for your accountant."
- "Legal interpretation is out of scope. The trustee or qualified counsel decides."

Do NOT route to:
- "your lawyer" (the user may not have one — never assume)
- A specific named individual (the skill is anonymous; named individuals live in the user's local files)
- Generic "consult a professional" (too vague, useless)

---

## What to do when the user has no lawyer

This is a common case (cost-cutting, conscious choice). The skill MUST work without a lawyer in the loop.

When a legal question arises:
1. Acknowledge it's a legal question
2. Document the underlying facts in the appropriate STATUS.md / decisions.jsonl
3. Add the question to the next trustee email draft (in `trustee-briefing.md` "Questions for the trustee" section)
4. Suggest the user includes it in the next scheduled trustee touchpoint
5. Do NOT freelance an answer

The trustee is the canonical legal/procedural authority for the insolvency case. Strategic decisions outside the trustee's scope (like personal asset protection beyond the proposal) may require external counsel — flag that the user can choose to engage external counsel if they wish, but do not assume they will.

---

## What about "advice" requests?

The user may ask "what should I do about X?". Distinguish:

- **Procedural** (how do I download état RP from CRA?) → in scope, give exact steps
- **Operational** (how should I organize this folder?) → in scope
- **Strategic** (should I dispute this creditor claim?) → out of scope, route to trustee
- **Legal** (am I personally liable for this?) → out of scope, route to trustee

If unsure, default to deferring. The cost of over-deferring is a slower workflow. The cost of giving bad legal advice is severe.

---

## Anti-pattern: invented advice

If you find yourself drafting a sentence that starts with "You could try..." or "Probably the best approach is..." for a legal/strategic topic, STOP. That's invented advice.

Correct pattern:
1. Document what's known (sourced)
2. Frame the question for the trustee
3. Wait for the trustee response before any action

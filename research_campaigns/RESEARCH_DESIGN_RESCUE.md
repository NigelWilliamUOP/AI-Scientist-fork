# Research-design rescue engine v0.2

This is a **diagnostic decision-support prototype**, not an autonomous peer reviewer or an evidence validator. It extends PR #9's counterfactual assessment with claim-specific rescue dispositions and a conceptual-plus-simulation route.

## Inputs
- Claim, type and independent scientific-review receipt
- Frozen study constraints; documented theoretical-value assessment
- Complete failure list from the existing review; identification and simulation feasibility decisions
- Rescue options stating the affected failure, proposed change, whether the original claim survives, feasibility, and a separate validation test
- Caller-supplied evidence admission IDs; these are **not** independently verified by this component

## Outcomes
- `passes_recorded_checks` only when a complete assessment has no failures
- `repairable_with_specified_test` when a claim-preserving feasible remedy exists; conditional, not an accomplished repair
- `requires_reframing_or_new_design` when a viable intervention changes the central proposition
- `redirect_to_conceptual_and_simulation` when an empirical identification route is assessed unavailable under frozen constraints, theoretical value is independently confirmed and a simulation is feasible
- `unresolvable_under_frozen_constraints` only on an explicit caller-provided impossibility finding
- `insufficient_information` otherwise

## Conceptual plus simulation contract
The resulting paper must formally specify constructs and mechanisms, contrast rival theories, list model assumptions and parameter provenance, run sensitivity and boundary-condition tests, derive observable predictions and disclose a future empirical identification route. **Synthetic outputs cannot validate the original empirical causal assertion.**

## Safeguards and limitations
- Preserve original claim ID, frozen constraint ID and external review receipt.
- Never suppress an unresolved failure because another flaw was repaired.
- Prefer a feasible claim-preserving empirical repair over a simulation redirection.
- Keep a repair scenario distinct from observed independent empirical success.
- No external sources, reviewer authenticity, feasibility, theoretical value or impossibility claims are verified here.
- A `validated_success` flag with admitted IDs is still caller asserted. This module must **not** be used to release the existing manuscript gates.
- Multi-failure repairs are not jointly optimised; a conditional disposition requires separately testing every affected dimension.
- No real peer-review acceptance-performance claims should be made from the synthetic unit tests.

## Test plan
`python -m unittest research_campaigns.test_research_design_rescue -v`

Before release, also run the full existing research_campaigns suite, perform adversarial tests of fake evidence receipts and conflicting expert judgements, and run a blinded assessment on actual studies. This draft is stacked on PR #9 and its earlier dependencies, not on main.

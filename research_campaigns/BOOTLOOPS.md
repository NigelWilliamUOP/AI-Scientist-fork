# Optional BootLoops verification adapter

Originally added 2 October 2026; integrated with the latest lifecycle and
IdeaScientist workflows on 10 October 2026. The arithmetic adapter is original
and BootLoops-inspired. The upstream toolkit was separately installed and tested
on the earlier branch. See BOOTLOOPS_INSTALLATION.md for the reproducible setup,
historical simulation control and validation limits.

Sources: https://bootloops.ai/harness.html and
https://github.com/BootLoops-ai/bootloops/tree/66b680ce742e654cfe86da4f072a69061fe182b1 .
Upstream code is MIT; upstream documentation is CC BY 4.0. No upstream code or
documentation is vendored. The upstream snapshot is pinned for reproduction. Its full package runner has
now been executed; receipts are in bootloops_selftest_results.json.

## Executable integration

Study Producer invokes this adapter when `--verify-arithmetic` is supplied.
It seals the admitted analysis inputs and actual calculation, then compares
supported fields against an independent rational calculation before requesting
the manuscript. Disagreement produces an abstention and blocks manuscript
generation. The verification policy is immutable for that study ID in its
workspace; a changed policy needs a new workspace.

```bash
python -m research_campaigns study \
  --brief brief.json --sources sources.json --workspace checked-study \
  --verify-arithmetic
```

For fixture data, also supply `--synthetic`. Python callers can use
`StudyProducer(ledger, session, verify_arithmetic=True)`. The default is false;
unchecked runs explicitly report `arithmetic_verification.status=not_requested`.

Programme Steward and Opportunity Scout can submit bounded descriptive/OLS
checks through the same API; unsupported methods must abstain or use a separately
reviewed adapter. They do not yet invoke it automatically. The challenge and
ideation harnesses remain separate from this Study Producer calculation gate.

```python
from research_campaigns.bootloops import seal, verify
# ledger is the lifecycle agent's existing core.Ledger.
# plan/source are the frozen analysis inputs; candidate is analysis["result"].
seal(ledger, "arithmetic-001", plan, source, candidate,
     role="study_producer", cutoff="2026-10-02T00:00:00Z")
report = verify(ledger, "arithmetic-001")
```

Sealing preserves the complete inputs, role, evidence dates, tolerance and source
checksum in the append-only ledger. A conflicting seal is rejected. Checks use
rational sums and normal equations independently of the existing centred
floating-point OLS implementation. A planted linear relationship exercises the
exact route; a deliberately incorrect slope exercises disagreement.
Declared integers are preserved before conversion to rational values. This
prevents the independent route from copying an earlier float-rounding error.

Run: `python -m unittest discover -s research_campaigns/tests -v`.
The integration tests exercise actual descriptive/OLS outputs, the CLI, an
intentionally corrupted calculation that passes same-route replay, the ordering
of verification before drafting, and immutable verification policies.

## Scope of the certificate

A passing report means agreement for the checked arithmetic fields on declared
decimal inputs. Measurement uncertainty, causal identification, construct validity,
novelty and independent journal review remain unverified. Sample standard
deviation and other unsupported fields are explicitly listed as unchecked.
A valid sealed prediction is an internal immutable record, not proof of prior
public registration or external timestamp authentication. Both routes see the
same data; this checks implementation, not independent evidence.

The seal enforces source availability and capture cutoff. It does not replace
the lifecycle source broker, authorisation controls or historical archive proof.
Callers must admit evidence through the existing broker first. Keep protected
SRO materials and private data outside public Git.

## Further upstream tools

For certified quadrature, Bayesian evidence or interval arithmetic, assess the
relevant upstream guide and dependency requirements before writing a reviewed
adapter. BootLoops' precision standard for analytic physics is not a general
acceptance threshold for empirical social science. The toolkit installer explicitly installs dependencies and runs upstream code.
The original adapter introduces no model-generated code execution. No paid model
call, empirical study, automatic claim promotion or global skill installation ran.

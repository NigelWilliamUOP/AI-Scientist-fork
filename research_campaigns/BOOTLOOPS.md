# Optional BootLoops verification adapter

Added 2 October 2026 to the three-agent lifecycle branch. This is an original,
BootLoops-inspired adapter, not an installation of the upstream toolkit.

Sources: https://bootloops.ai/harness.html and
https://github.com/BootLoops-ai/bootloops/tree/66b680ce742e654cfe86da4f072a69061fe182b1 .
Upstream code is MIT; upstream documentation is CC BY 4.0. No upstream code or
documentation is vendored. The upstream snapshot is recorded for attribution,
not a claim that its full suite ran here.

## Executable integration

Study Producer can pass its existing analysis result into this adapter.
Programme Steward and Opportunity Scout can submit bounded descriptive/OLS
checks through the same API; unsupported methods must abstain or use a separately
reviewed adapter. No agent automatically invokes this module.

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

Run: `python -m unittest discover -s research_campaigns/tests -v`.

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
acceptance threshold for empirical social science. No arbitrary command execution,
dependency installation, paid model call, empirical study, automatic claim
promotion or global skill installation is introduced by this addition.

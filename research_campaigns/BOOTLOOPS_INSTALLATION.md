# BootLoops toolkit installation, 2 October 2026

The actual upstream toolkit is installed in this execution workspace at
/workspace/scratch/d7aa5a24f074/bootloops, with an isolated .venv.
Upstream checkout: 66b680ce742e654cfe86da4f072a69061fe182b1.
This workspace may be transient; the installer and pinned dependencies in this
branch reproduce the installation on another machine.

## Validation

Full upstream runner: 49 packages, 42 PASS, 4 FAIL, 3 REFUSED by design.
PASS includes partial and smoke batteries and their named skipped legs; it is
not a claim that every engine or data-dependent calculation was tested.
Python dependency consistency: pip check passed.

Not validated for use here:
- Abacus: cypari2 missing (requires PARI/GP).
- Counterweight: Julia missing.
- AMFlow-kit: seven process/PID discovery tests failed; 43 passed, 3 skipped.
- Seedling: cgroup process ancestry control failed (12 tests passed before stop).
The process failures occur in this container; PID namespace compatibility is a
suspected cause, not a demonstrated fix. Do not use these resource-control
components as validated safeguards here.
- FFCapital, Frobenius-boundary and Galois: reference-data or prerequisite gates.
- Separate Turnstile operations battery: 22 passed, 1 failed (daemon-reaping
positive control could not plant a process). It is not validated here.

Kira, Blade, AMFlow.cpp and other compiled external engines have not been built.
The full source toolkit is present; engine-dependent paths remain conditional.

## Simulation use

Baller, ERAS, Mixalot, Popcorn and other available tools passed their declared
batteries with the qualification above. Consult each tool's GUIDE and run controls
for the actual model before adopting it.

Executed upstream Baller on Muller's recurrence (synthetic numerical control):
ordinary float x100 = 100.0; 50-digit ball arithmetic marks UNCERTIFIED;
adaptive arithmetic renders 6.000000016099565 at 16 requested digits.
The solver reported 79 certified digits at 240 working decimal digits.
This checks numerical behaviour, not empirical validity or model uncertainty.

Run the saved control:
```bash
BOOTLOOPS_ROOT=/absolute/path/bootloops /absolute/path/bootloops/.venv/bin/python \
  research_campaigns/bootloops_simulation_control.py
```

Reproduce toolkit setup:
```bash
bash research_campaigns/install_bootloops.sh /absolute/path/bootloops
```
The installer returns nonzero if any upstream battery fails, retaining its
selftest_results.json. Expected unavailable tools are never relabelled PASS.
The original bootloops.py verifier remains opt-in. No legacy launcher, scientific
baseline, study evidence or agent default has changed. No paid model calls ran.

# OSINT Bayes / working evidence observatory 0.4.1

A working first release for the HEIF demonstrator, built from the supplied v0.4 specification. It runs a real FastAPI/SQLite application behind a native TypeScript interface. The five attributed Portsmouth records are real, bounded source extracts, not invented demo events. This release is **not yet live-integration-qualified**: original web capture, paid model execution, Google Drive OAuth/readback and public deployment must pass on the chosen host.

## Start the ready-to-run release

Install Python 3.11 or later. Unzip the whole release, retaining its directories. On Windows, double-click `START_WINDOWS.cmd`. On macOS/Linux, run `sh start.sh` from this directory. The first launch creates a private `.venv` and downloads pinned Python dependencies; it does not make AI calls or provision hosting.

Alternatively, in a terminal:

```sh
python scripts/bootstrap.py
```

Open `http://127.0.0.1:8000`. The launcher prints the location of the generated owner password, `.runtime/secrets/owner-password.txt`. Enter that password in the browser. Do not share the owner password with reviewers. Stop with Ctrl+C. The database remains in `.runtime/`.

For a prepared Python environment:

```sh
python -m pip install -r requirements.txt
python scripts/run.py
```

Do not install the parent AI-Scientist repository's requirements. This app is isolated.

The downloaded release includes compiled `frontend/public/app.js`. The GitHub source tree keeps TypeScript as the source of truth: from a fresh clone, build it with Node 22 before launching Python:

```sh
cd frontend
npm ci --ignore-scripts
npm run build
cd ..
python scripts/bootstrap.py
```

The Dockerfile builds the interface automatically. A bootstrap from source attempts the same npm build when compiled JS is absent and Node/npm is available.

## What works without external keys

The source explorer opens exact retained passages, publication metadata and checksums. The evidence network keeps equipment procurement separate from the operations procurement and connects the actual title correction to its tender. The timeline reconstructs two publisher-time cut-offs on 5 October 2024, excluding undated material and any later assessment. This is retrospective reconstruction, never a claim of contemporaneous observation.

Withdraw a source to remove its graph node and its supported statements from the scenario. Compile a template-based evidence briefing, inspect its citations, then explicitly record a human review. The template does not answer arbitrary questions and is never labelled AI. Review decisions are versioned; concurrent or stale approval is rejected. Reviewer logins are separate sandboxes; only the owner can collect originals, accept shared assessments or authorise Drive.

Export a protected ZIP containing admitted records, any admitted original captures, the briefing, review state, model-run records, activity records and a checksum manifest. Restore into a read-only snapshot without overwriting the current shared assessment. Hash checks establish internal byte consistency, not cryptographic proof of publisher authenticity or resistance to an administrator rewriting the database.

The separate synthetic sensitivity lab demonstrates replacement rather than accumulation of revised evidence. It does not assign a probability to the real Portsmouth project.

## Real evidence and collection

`seeds/manifest.json` identifies all five source files and their hashes. The extracts came from the user-supplied Codex v0.4 pack. No original HTTP snapshots are bundled. Four fixed government notice URLs are allowed for collection; the port-news record remains excerpt-only. This is not an unrestricted web scraper.

Click **Refresh originals** as the owner. The backend records a real retrieval attempt, captures successful original HTML, runs a bounded parser and records the outcome. An unchanged record remains unchanged. An inaccessible source or an unfamiliar layout is reported explicitly, with previous evidence preserved. If parsing fails after retrieval, the original bytes remain in the capture store for developer inspection. The parser has been tested against fixtures assembled from the retained passages, not against successful fresh publisher responses in this sandbox.

The contextual map pin is the port's own visitor-directions coordinate, `50.811823, -1.088367`, sourced from <https://portsmouth-port.co.uk/at-the-port/find-us/>. It is not a surveyed equipment position. Optional OpenStreetMap tiles load only after an explicit click, with browser caching and attribution; no tiles are bundled or downloaded for offline use. The network remains usable without a base map. OSM tile policy: <https://operations.osmfoundation.org/policies/tiles/>.

## Enable AI on the server

The earlier reference to an “OpenRefine key” has not been confirmed. This implementation is specifically for **OpenRouter**, not OpenRefine. Do not paste the key into ChatGPT, browser fields, commits or GitHub issues.

For local use, copy `.env.example` to `.env` and fill it privately. On a hosted service, use its secret store. Required settings:

```text
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<server-side capped key>
OPENROUTER_MODEL=<exact author/model identifier, not a latest alias>
OPENROUTER_PROVIDERS=<explicit approved endpoint identifiers, comma-separated>
ALLOW_PAID_AI=true
```

The owner must choose and approve the endpoint. The adapter checks the endpoint metadata for structured-output support and a conservative price bound before reserving spend atomically. Unknown pricing or unsupported endpoints fail closed. Unknown billed cost remains reserved rather than being presented as zero. Use a provider-side credit limit too; application estimates cannot guarantee a provider's bill. Defaults are $0.25 per call, $5 per session and $20 per UTC day across the instance. A second-pass challenge consumes a separate call and budget reservation. Failed paid calls are not retried automatically.

AI receives only the selected passages and the submitted question; it has no tools, browser, shell, GitHub access or Drive-write permissions. Each factual statement must cite an admitted source version and exact retained quotation. Mechanical quote checks do not establish semantic support: human review remains necessary. The second pass is another model call, not a Luna agent or an independent human adjudicator. Raw model reasoning is not requested. Provider/model/request identifiers, usage, returned cost when available and output checks are recorded.

Documentation: <https://openrouter.ai/docs/guides/features/structured-outputs>.

## Connect Google Drive

The ChatGPT Drive connection does not transfer credentials to this application. Create an owner-authorised Google OAuth web client. Its redirect URI must exactly equal:

```text
<APP_PUBLIC_URL>/api/v1/owner/drive/callback
```

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and a private Fernet `TOKEN_ENCRYPTION_KEY` in the server environment. Generate a key with:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then use **Connections → Connect owner's Google Drive**. The application requests `drive.file` only and creates its own `OSINT_Bayes_HEIF` folder; it does not search the user's wider Drive. Refresh credentials are encrypted on disk. After creating an export, choose **Verify upload to Drive**. A successful upload is downloaded again and hash-checked; the Drive manifest is uploaded last and also checked. Failed sync remains pending; the local ZIP is retained. Repeating a sync reuses the same content object.

This version implements owner OAuth, not service-account/Shared Drive deployment. The 4.5 MB compressed export limit is explicit. Larger archives need a later resumable/chunked extension. SQLite is the working transaction store; Drive is the archive, not a concurrently edited database.

Google upload documentation: <https://developers.google.com/workspace/drive/api/guides/manage-uploads>.

## GitHub and deployment

Repository: `NigelWilliamUOP/AI-Scientist-fork`.
Source branch: `agent/heif-visual-osint-web-v0-4`.
Application directory: `demos/bayesian-osint/webapp/`.

GitHub Pages is static hosting and cannot safely run the Python backend or hold the provider key. Use the supplied Dockerfile on an approved host, with a persistent writable `/data` volume, one process/one instance, and HTTPS in front of the service. Set `APP_ENV=production`, `APP_PUBLIC_URL` to the exact HTTPS origin, and a long `APP_OWNER_PASSWORD`. An optional distinct `APP_REVIEWER_PASSWORD` enables isolated reviewer sandboxes.

`deploy/render.yaml.example` is an owner-reviewable example, not a provisioned service. Persistent hosting may incur charges; nothing has been purchased or deployed by this release. Confirm current provider configuration, filesystem permissions, prices and institutional requirements before launch. `compose.yaml` binds only to the local loopback interface. `deploy/app-ci.yml.example` can be enabled explicitly; it is not an assertion that GitHub Actions has run.

Before a funding review, the owner should see successful records of: a fresh government-source capture, an actual grounded model response, a source-removal challenge, verified Drive readback and persistence after a real host restart. Do not mark the application reviewer-ready based on mocks or configuration status.

## Verify and restore

```sh
python scripts/validate_pack.py
python -m pip install -r requirements-dev.txt
python -m pytest -q backend/tests
# Against a running local server, set BROWSER_TEST_PASSWORD in your shell:
python scripts/browser_check.py
python scripts/archive.py verify path/to/export.zip
# Stop the server first; restore only a trusted owner-exported bundle:
python scripts/archive.py restore path/to/export.zip --data-dir .runtime
```

The browser needs an installed Playwright Chromium (`python -m playwright install chromium`), or `--chromium /path/to/chromium`. The sandbox verification used `--asgi-bridge` because its browser blocks HTTP navigation. That mode tests the actual app logic through an in-process adapter; it is not a native browser-to-host connectivity/TLS/cookie test. See `reports/BUILD_REPORT.md` for exactly what ran and what remains blocked.

## Boundaries and maintenance

This is a single-owner HEIF demonstrator for public information. It is not an accredited intelligence service, production multi-tenant platform, air-gapped deployment, general autonomous-research agent or legally approved information-processing service. No individual profiling, face recognition, private-source collection or operational vessel surveillance is implemented. Add institutional security/privacy review before broad deployment or sensitive use.

Preserve `.runtime/` and the separately held encryption key in an approved owner backup. Evidence exports intentionally exclude credentials and authentication records. Use API-mediated changes; do not edit the SQLite database while the service is running. Interrupted work is visibly failed/pending and requires deliberate retry. One worker is intentional; do not scale to multiple replicas on SQLite.

The browser uses dependency-free native TypeScript/DOM/SVG rather than the earlier planned React/Vite stack. This removed a package-registry dependency during development while retaining a typed source and a functioning frontend/backend boundary. The original reference arithmetic, citation validator and bounded collector are retained as small modules. Do not introduce speculative LLM confidence numbers into the real evidence case.

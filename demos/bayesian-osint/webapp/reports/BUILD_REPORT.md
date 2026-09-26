# OSINT Bayes 0.4.1: build and validation report

Date: 26 September 2026. Status: **working local application; live integrations and public deployment not qualified**.

## Delivered implementation

A native TypeScript/DOM/SVG interface backed by FastAPI, SQLite and one persisted job worker. It includes authenticated owner and isolated reviewer sessions; the real-source explorer, provenance network, contextual map and historical timeline; exact-passage inspection; source withdrawal; template briefing; explicit review acceptance; frozen snapshots; audit ZIP export and restore. The OpenRouter and owner-OAuth Google Drive adapters are implemented behind disabled/unconfigured states until credentials and approval are provided.

The interface uses native TypeScript instead of the earlier proposed React/Vite stack. This allowed compilation without downloading a frontend framework. The release ZIP includes the compiled browser asset; the GitHub source checkout compiles it with Node 22 and TypeScript 5.8.3.

No Luna/subagent execution facility was available in this session. The implementation was built directly. No model key was used and no paid hosting was provisioned.

## Observed checks

| Check | Observed result | Scope |
|---|---|---|
| Python suite | 131 passed, 21 subtests passed | 65 application tests plus 66 retained reference tests. The subtests are not counted as additional top-level tests. |
| TypeScript compilation | Passed | Strict compilation into the release browser asset. |
| Chromium interface checks | 49 passed, 0 failed, 0 page errors | Real compiled JS/CSS, actual FastAPI application through an in-process ASGI bridge. |
| Native local HTTP API | Passed | Health, login, queued template job and local archive download/hash. |
| Seed integrity | Passed | Five attributed extract files and their segment/file checksums. |
| App original-source requests | 0 successful, 4 unavailable | Actual attempts from this runtime; outbound access unavailable. Previous records preserved. |
| Actual model inference | Not run | No key or approved model/provider supplied. Mock tests are not live evidence. |
| App Google OAuth / Drive upload | Not run live | Adapter tested with controlled fixtures. No owner credentials supplied to app. |
| Docker build / clean dependency installation | Not run | Docker absent; package-registry access unavailable. |
| Public deployment / hosted HTTPS | Not run | No hosting service provisioned. |

`pytest.xml`, `pytest-log.txt`, `browser-results.json`, `source-integrity.json` and `local-http-probe.json` contain the underlying local records. Browser screenshots were captured from the actual interface, not drawn as mock-ups. All test credentials are labelled fixtures; runtime secrets and databases are excluded from this release.

## Browser-test qualification

Chromium in this sandbox rejects HTTP navigation, including loopback, with `ERR_BLOCKED_BY_ADMINISTRATOR`. The browser suite therefore loaded the compiled application into `about:blank` and connected fetch calls to the actual in-process FastAPI application. No business answers or source-selection behaviour were mocked for those 49 checks. This validates DOM behaviour and API interaction, not native browser HTTP transport, cookie enforcement, TLS, external map tiles or hosting. Native HTTP API operation was verified separately using an HTTP client.

## Data qualification

The five Portsmouth records are short, attributed extracts from the user-supplied v0.4 pack. They are labelled `curated_web_extract`, with no invented capture time or upstream HTTP hash. They are not original HTTP snapshots. The collector accepts four fixed government URLs; the port statement remains excerpt-only. Collection parsing has been tested on synthetic HTML assembled from the retained passages, not fresh publisher HTML. An unexpected live layout must fail visibly and may require a parser adjustment on the chosen host.

Historical reconstruction uses conservative publication-time boundaries and excludes undated material. It does not claim the system observed the documents in 2024. The actual correction is a title repair, not a changed operating date. Numerical Bayesian examples belong only to the separate synthetic sensitivity lab; there is no calibrated probability for the real project.

## Representative protections exercised

The tests cover role/CSRF/origin checks, source exclusion from graph and citations, prevention of later metadata leaking into historical views, explicit human acceptance, rejection of stale review, persistence across restart, and preservation of an earlier assessment in frozen replay. Controlled integration tests cover capture failure/raw preservation, exact-quote validation, conservative model pricing and atomic budget reservation, encrypted OAuth credentials, Drive readback mismatch, deduplication and manifest-last ordering.

Matching quotations do not prove an interpretation. Archive hashes establish byte integrity, not publisher authenticity, digital signatures or protection against an administrator rewriting the database. This is not a security accreditation.

## Required before a live funding demonstration

Run on an approved host with outbound connectivity and persistent storage. Verify the four original government records and inspect parsing; configure the confirmed AI provider/model with a capped server-side key; authorise the app's own Google OAuth client; verify an actual model response and Drive byte readback; run the native-browser suite and restart the host without losing the accepted assessment. The supplied `scripts/verify_live.py` records those actions only when explicitly requested.

Saving this release through ChatGPT's existing Drive connector is a delivery action, not validation of the application's separate Google OAuth integration.

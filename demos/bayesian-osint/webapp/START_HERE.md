# Start the working OSINT Bayes application

This is application code, not another Codex assignment. The downloaded ZIP includes the built browser interface, backend, five real evidence extracts, tests and deployment files. No Codex chat is needed to run it.

## Windows

Install Python 3.11 or later. Extract the entire ZIP into a normal local folder. Double-click `START_WINDOWS.cmd`. The first launch downloads pinned dependencies into a private environment, so internet access is needed. It does not call AI or buy hosting.

Open `http://127.0.0.1:8000` in your browser. The terminal identifies the private owner-password file at `.runtime/secrets/owner-password.txt`; open that file locally and enter its contents into the login screen. Leave the terminal running while using the app. Stop with Ctrl+C. Keep the `.runtime` folder to retain evidence and reviews.

## macOS or Linux

From the extracted application folder, run `sh start.sh`, then follow the same browser/password steps. A terminal alternative on any supported platform is `python scripts/bootstrap.py`.

## First demonstration, without keys

Use the source explorer and network to inspect a record. Open the publication timeline and compare the two October 2024 cut-offs. Return to Current investigation, withdraw the equipment source with its minus control and compile an evidence brief. The source-dependent wording disappears. Reinstate the source, compile again, inspect the citations and explicitly accept the wording. Export the resulting audit ZIP. These are backend operations, not a scripted slide show.

The template briefing uses no AI and cannot answer arbitrary questions. The separate sensitivity lab uses illustrative Bayesian assumptions, not a forecast for the Portsmouth case. Real retained extracts are available immediately; successful fresh collection still needs verification on your computer or host.

## AI, Drive and reviewer access

The implemented model adapter is OpenRouter. The earlier term “OpenRefine key” remains unconfirmed. Use `.env.example` privately for local configuration or a hosting secret store; do not paste keys into chat or GitHub. The README lists exact model/provider, budget and approval settings.

Google Drive needs the application's own owner-authorised OAuth client. Your ChatGPT Drive connection cannot supply those credentials to a web app. The implementation archives to an app-created folder and marks success only after checking the downloaded bytes. Until then, local export remains available.

Do not share the owner password. A distinct `APP_REVIEWER_PASSWORD` enables isolated reviewer sessions; a reviewer cannot overwrite the owner's accepted assessment or authorise Drive.

## GitHub source and hosting

Repository: `NigelWilliamUOP/AI-Scientist-fork`.
Branch: `agent/heif-visual-osint-web-v0-4`.
Directory: `demos/bayesian-osint/webapp/`.

A GitHub checkout needs the TypeScript compilation step in the README; the downloaded release ZIP already includes it. Run only this application's launcher, not the parent AI-Scientist dependency setup.

A public reviewer link requires hosting the backend. Docker and a Render example are supplied, but no service has been provisioned and no public URL exists yet. Review the remaining checks in `reports/BUILD_REPORT.md` before presenting any integration as live.

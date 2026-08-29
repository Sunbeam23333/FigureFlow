# Security policy

## Supported version

Security fixes are applied to the latest commit on the default branch. This is a demonstration project, not a managed multi-tenant service and not a security boundary for confidential documents.

## Reporting a vulnerability

Please use GitHub's private **Report a vulnerability** flow for this repository when it is available. Include the affected commit, reproduction steps, impact, and a minimal proof of concept. Do not include API keys, private documents, personal data, or a live exploit against a public deployment.

If private vulnerability reporting is not enabled, open a minimal issue requesting a private contact channel. Do not publish exploit details or secrets in that issue. Please avoid testing against infrastructure you do not own or have permission to assess.

## Deployment boundary

- Treat `OPENAI_API_KEY` as a server-side secret. Never expose it in Gradio inputs, browser code, URLs, screenshots, logs, manifests, Docker layers, or committed environment files.
- Online mode sends the submitted brief to the configured OpenAI model. Do not submit confidential or regulated material unless the deployment, account, data handling, and organizational policy have been approved for it.
- Offline replay avoids the semantic-planning API call, but it should not be interpreted as a general air-gap guarantee. Audit the runtime and disable outbound network access when an air-gapped deployment is required.
- Generated artifacts can repeat the user's input. Apply retention limits, access control, cleanup, and redaction to `demo/output/` and downloaded ZIP files.
- Set `FIGUREFLOW_PUBLIC_DEMO=true` for an unauthenticated public link. This forces the fixed synthetic offline replay, ignores custom briefs, and disables live model/icon calls.
- For any reachable online deployment, set `FIGUREFLOW_BASIC_AUTH_USER` and `FIGUREFLOW_BASIC_AUTH_PASSWORD`, retain the default one-worker/eight-item queue or stricter limits, and set `FIGUREFLOW_MAX_RUNS` to a bounded value.
- Run the service as an unprivileged user, keep dependencies updated, restrict public ingress, set request size and rate limits at the reverse proxy, and terminate TLS before exposing it beyond localhost.
- The public Demo should not accept arbitrary paths, executable code, TeX, archives, or unrestricted file uploads. Keep layout and asset selection on an allowlist.

## Model-output boundary

Model output is untrusted data. FigureFlow validates it against a strict Pydantic schema and only permits known layout, theme, accent, evidence-status, and asset identifiers. Do not weaken this boundary by evaluating model-produced Python, shell, HTML, JavaScript, TeX, or filesystem paths.

All subprocess calls should use argument arrays with `shell=False`, fixed local scripts, resolved project-owned directories, timeouts, and checked exit codes. Never interpolate the user's brief into a command.

## Before sharing a run

1. Confirm that the preview contains no confidential names, screenshots, identifiers, formulas, or metrics.
2. Inspect plan, metadata, manifest, and logs for user text and local paths.
3. Confirm that no `.env`, API key, response payload, or debug traceback is included.
4. Verify generated images and prompts for copyright, trademark, privacy, and policy concerns.
5. Delete the run directory when retention is no longer required.

# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Email sending safety (`MAIL_DRY_RUN`)

`EmailService.approve_and_send` (`app/services/email_service.py`) is gated by
`MAIL_DRY_RUN` (default `true` in `app/config.py`). While enabled, all sends are
redirected to `DRY_RUN_RECIPIENT` regardless of `lead.email`, with a log line
naming the real intended recipient. Set `MAIL_DRY_RUN=false` only when you
intend to email real businesses; there is no other gate on the real send path
besides the existing "must be APPROVED" status check.

## `lead.confidence` is recomputed at three points

`compute_confidence` (`app/core/scoring.py`) is called three times per lead,
each time with different `html_generated`/`email_drafted` flags, and the
result is persisted each time:
1. `SiteAnalyzer.analyze` — both flags `False` (html/email don't exist yet).
2. `HTMLGenerator.generate` — `html_generated=True`.
3. `EmailService.draft_email` — `email_drafted=True`, `html_generated` derived
   from whether `lead.html_path` is already set.

If you add a new scoring dimension gated by a later pipeline stage, recompute
and re-save `lead.confidence` at that stage too, or the new dimension will be
permanently stuck at its zero-value default like `html_quality`/
`outreach_confidence` used to be (see git history for the original bug).

## Unconfigured AI falls back to a generic template — loudly

With no `.env` (or `LLM_PROVIDER=mock`, or a blank/`your-api-key-here`
`LLM_API_KEY`), `HTMLGenerator.generate` still succeeds: it writes the generic
industry template from `_generate_fallback_html` with `quality_score=50` and
the lead reaches `REDESIGN_GENERATED`. Historically this was silent and looked
like a real AI result across machines. It is now loud:
`llm_unconfigured_reason()` (`app/core/llm_provider.py`) detects mock mode and
blank/placeholder keys, `app/main.py` logs a WARNING banner at startup, and
`generate()` logs WARNINGs (module logger + `lead.add_log`) whenever the
fallback is used because the AI was unavailable or the LLM call failed —
distinct from the AI running and the critic scoring low, which keeps the AI's
HTML and is never labeled a config failure. If output looks like the same
boilerplate hero/cards/testimonial page for every lead, check the logs for
"AI NOT CONFIGURED" / "NOT an AI-generated design" before debugging anything
else, and fix `.env` (`LLM_PROVIDER` + `LLM_API_KEY`).

Until this same change, `HTMLGenerator._plan` also referenced
`DESIGN_PLAN_PROMPT`, `HTML_CRITIQUE_PROMPT`, and `HTML_REVISION_PROMPT`
without importing them from `app.core.prompts`, so every call raised
`NameError` and hit the `except Exception` fallback path — even a correctly
configured, real LLM provider always silently produced the generic template.
That import bug is now fixed, so the AI-ran-vs-fallback distinction above is
meaningful; if it regresses, real AI output will disappear again without any
config-looking symptom.

## `Database` ignores `DATABASE_URL`

`Database.__init__` (`app/storage/database.py`) always opens
`settings.data_dir / "app.db"` — the `DATABASE_URL` env var/setting is read
into `Settings` but never consulted for the actual connection path. Tests that
set `DATABASE_URL` to a tmp path are not actually isolating the database file;
they still read/write the real `data/app.db` in the repo. This is pre-existing
behavior, not something introduced by tests — be aware of it if a test's
assertions seem to depend on stale state from a previous run.

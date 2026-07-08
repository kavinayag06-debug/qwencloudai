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

## `Database` ignores `DATABASE_URL`

`Database.__init__` (`app/storage/database.py`) always opens
`settings.data_dir / "app.db"` — the `DATABASE_URL` env var/setting is read
into `Settings` but never consulted for the actual connection path. Tests that
set `DATABASE_URL` to a tmp path are not actually isolating the database file;
they still read/write the real `data/app.db` in the repo. This is pre-existing
behavior, not something introduced by tests — be aware of it if a test's
assertions seem to depend on stale state from a previous run.

# Analytics boundary

This app stores privacy-safe playtest events only. Call `record_analytics` with
an allowlisted event type and aggregate properties. Raw Secret, Guess, Feedback,
token, display name, guest ID, IP, user agent, or arbitrary payload is rejected
by design. Analytics consumes outcomes and never changes Match state.

Export aggregate counts with:

```bash
uv run python manage.py export_playtest_analytics --format json --since-days 30
```

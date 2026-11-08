# Test Report — Tanding.in 1.2.3

**Reported execution date:** 8 November 2026  
**Environment:** WSL Ubuntu, Python 3.14  
**Command:** `python3 -m unittest discover -s tests -v`

## Result

**10 tests passed, 0 failed, in 2.557 seconds.** The terminal output supplied by the project owner shows no `ResourceWarning` or `DeprecationWarning` in this run.

| Test | Result |
|---|---|
| `test_vercel_config_has_entrypoint_and_excludes_non_runtime_files` | PASS |
| `test_vercel_edge_headers_cover_static_and_private_api` | PASS |
| `test_auth_rules` | PASS |
| `test_full_flow` | PASS |
| `test_security_headers` | PASS |
| `test_timestamp_factory_returns_utc_naive_value` | PASS |
| `test_upload_size_and_extension_validation` | PASS |
| `test_file_tokens_round_trip_and_are_not_direct_blob_urls` | PASS |
| `test_local_private_storage_round_trip` | PASS |
| `test_vercel_adapter_enforces_private_access_for_put_and_get` | PASS |

## Scope and limitations

The passing suite verifies local application behavior, route/authentication rules, upload validation, storage adapter behavior with a fake Vercel client, and deployment configuration. It does **not** prove that production PostgreSQL or Vercel Blob credentials work.

The following checks remain outstanding:

- Live PostgreSQL connection and Alembic migration.
- Real Vercel Blob Private PUT / GET / DELETE operations.
- GitHub Actions workflow execution and `pip-audit` result after repository creation.
- Vercel build, preview deployment, runtime smoke tests, and production verification.

## Reproduction

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q app.py models.py storage.py migrations scripts tests
node --check public/js/app.js
```

# Tanding.in — Deployment Runbook (Vercel Hobby)

This runbook is for the **project owner's** accounts and should be followed in order. It does not authorize deployment by itself; the project owner must approve the final deployment gate.

## 0. Ownership and prerequisites

- GitHub owner: `shifi06` (verify this is the friend's account before publishing).
- Repository: `tandingin`, visibility **Public**, default branch `main`.
- Vercel account/team: the friend's personal Hobby account.
- Vercel's GitHub Login Connection must point to the same friend's GitHub account.
- Keep the Git commit identity honest and associated with the actual author; do not rewrite author metadata to bypass Vercel's Hobby restrictions.
- Never put `.env`, `.env.local`, database dumps, uploads, tokens, passwords, or personal evidence into the public repository.

Vercel documents automatic deployments from Git providers and recommends a production branch such as `main`. Review its current Git deployment and Hobby-team rules before the first push. <https://vercel.com/docs/git>

## 1. Publish the source repository

1. Create a new public repository named `tandingin` under the friend's personal GitHub account.
2. Upload the contents of this project directory (the directory containing `app.py`, not its parent ZIP-extraction folder).
3. Confirm `main` contains `README.md`, `app.py`, `models.py`, `storage.py`, `public/`, `migrations/`, `tests/`, `.github/workflows/ci.yml`, and `vercel.json`.
4. Confirm `.env`, `.env.local`, `.venv/`, `0-0/`, `instance/`, `*.db`, `*.sqlite*`, and uploaded evidence are not tracked.
5. Wait for GitHub Actions. Do not connect Vercel until the CI job is green.

## 2. Create the Vercel project

1. Sign in to the friend's Vercel account.
2. Confirm the connected GitHub provider account is the same owner as the public repository.
3. Select **New Project** and import `shifi06/tandingin`.
4. Set project name to `tandingin`, root directory to the repository root, and production branch to `main`.
5. Keep Flask auto-detection; do not force Next.js, add a Node build command, or set a static output directory.
6. Do not trigger the first production deployment until the required environment variables and managed services are configured.

Vercel's Flask runtime detects a top-level WSGI `app` instance in root `app.py`; static assets belong in `public/`. Python 3.14 is supported. <https://vercel.com/kb/guide/ship-a-flask-app-on-vercel>

## 3. Provision PostgreSQL

1. From the Tanding.in Vercel project, open **Storage / Marketplace** and provision a Neon PostgreSQL database dedicated to Tanding.in.
2. Do not reuse OLION's database.
3. Configure a pooled runtime URL as `DATABASE_URL`.
4. Configure the direct/unpooled connection as `DATABASE_URL_UNPOOLED` or `MIGRATION_DATABASE_URL` for schema/data migrations.
5. Use separate Neon branches/databases for Preview and Production where available; never point preview tests at production data.
6. Require TLS/SSL as specified by the Neon connection string.

## 4. Provision private file storage

1. In the Tanding.in project Storage page, create a new Vercel Blob store named `tandingin-private-files`.
2. Set access to **Private** at creation time. It cannot be converted from public to private later.
3. Connect the store to the Tanding.in project and the intended environments.
4. Prefer the supported Vercel OIDC + `BLOB_STORE_ID` integration. The Python SDK also supports `BLOB_READ_WRITE_TOKEN` as an alternative.
5. Do not place Blob tokens in GitHub or the public source repository.

The Vercel Python Blob SDK supports the synchronous `put_blob`, `get_blob`, and `delete_blob` methods and requires `access="private"` for a private store. <https://vercel.com/docs/vercel-blob/python-sdk-reference>

## 5. Configure environment variables

Set these on the Vercel project (Preview and Production as appropriate):

| Variable | Required value / purpose |
|---|---|
| `SECRET_KEY` | A long, randomly generated secret unique to Tanding.in |
| `DATABASE_URL` | Neon pooled PostgreSQL URL for runtime |
| `DATABASE_URL_UNPOOLED` | Neon direct URL for migration, if provided |
| `MIGRATION_DATABASE_URL` | Optional explicit migration URL; takes precedence in migration mode |
| `STORAGE_BACKEND` | `vercel_blob` |
| `BLOB_STORE_ID` / OIDC | Injected by Vercel when the Private Blob store is connected |
| `BLOB_READ_WRITE_TOKEN` | Only if using a manual token instead of OIDC integration |
| `ADMIN_EMAIL` | Initial Super Admin email, for first bootstrap only |
| `ADMIN_PASSWORD` | Strong unique initial password, for first bootstrap only |
| `AUTO_INIT_DB` | `0` (never auto-create production schema on Function startup) |

After the first Super Admin is created, remove `ADMIN_PASSWORD` from Vercel environment variables. Keep all secrets encrypted/sensitive and never paste them into issue comments or chat.

## 6. Run schema migration and bootstrap

Run these operations from a trusted local machine using the project source. Install dependencies, link the Vercel project, and pull environment variables into a local ignored file:

```bash
vercel link
vercel env pull .env.local
set -a
source .env.local
set +a
python -m pip install -r requirements.txt
TANDINGIN_DB_MIGRATION=1 flask --app app db upgrade
flask --app app bootstrap
```

If migrating an existing SQLite database, do **not** run `bootstrap` before the importer. The importer requires all destination tables to be empty. Instead:

```bash
TANDINGIN_DB_MIGRATION=1 flask --app app db upgrade
python scripts/migrate_sqlite_to_postgres.py /path/to/tandingin.db \
  --legacy-upload-dir /path/to/instance/uploads
flask --app app bootstrap  # only if the imported database lacks roles/admin
```

Take a backup of the SQLite database and upload directory first. The importer copies rows and primary keys, uploads legacy `/uploads/...` images into Private Blob, updates PostgreSQL sequences, and refuses to merge into a non-empty target. Inspect row counts and sample records after import.

## 7. Preview validation / smoke tests

Before promoting `main` to Production, validate the Preview deployment. At minimum:

- `GET /` returns the Tanding.in page.
- `GET /css/style.css` and `GET /js/app.js` return successfully.
- `GET /api/auth/me` returns an unauthenticated response payload without leaking data.
- Wrong credentials return `401`; protected routes reject anonymous users.
- Registration creates only a `kapten` role for public self-registration.
- Super Admin can create a Panitia; unrelated Panitia cannot modify another organizer's tournament.
- Team registration, schedule conflict checks, result upload, approve/reject, and re-upload all work.
- Private file download is allowed only to the relevant team captains, the owning Panitia, and Super Admin; unrelated users receive `403`.
- Blob store reads/writes/deletes use the Private store successfully.
- Review Vercel Function logs for database, Blob, and import errors.

Upload requests are intentionally limited to 4 MB per file because Vercel Function request/response payloads have a 4.5 MB cap. <https://vercel.com/docs/functions/limitations>

## 8. Production go-live gate

Production deployment is allowed only after:

- [x] v1.2.3 full test suite passes locally (10 tests; no warnings shown in the owner's submitted WSL output).
- [ ] GitHub Actions test, compile, JS syntax, and `pip-audit` checks are green.
- [ ] Neon migration/bootstrap or SQLite import has been verified.
- [ ] Real Private Blob PUT/GET/DELETE and authorization checks pass.
- [ ] Preview smoke tests pass.
- [ ] Project owner authorizes production deployment.

Merge/push to `main` only after approval. Vercel automatically creates a Production deployment for the configured production branch.

## 9. Rollback and operations

- For an application regression, revert the offending Git commit and redeploy the previous known-good revision.
- Do not assume a code rollback reverses a database migration. Prefer additive migrations; take a database backup before destructive schema changes.
- Keep a periodic database export/backup outside the public repository. Test restoration before relying on it.
- Monitor Vercel Function logs, Neon usage/connection count, Blob storage/transfer usage, and Hobby limits.
- Vercel Hobby is intended for personal/non-commercial use; do not use it for a commercial service without reviewing and changing the plan.

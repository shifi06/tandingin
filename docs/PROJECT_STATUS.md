# Tanding.in — Project Status & Delivery Plan

**Release candidate:** 1.2.3  
**Project type:** Academic / portfolio e-sports tournament management application  
**Target hosting:** Vercel Hobby  
**Repository owner:** GitHub account `shifi06` (confirmed connector identity in the conversation)  
**Vercel owner:** `shifi06` Hobby account (now matches the connected GitHub identity).

## Executive summary

Tanding.in has been adapted from a local Flask + SQLite + filesystem-upload application into a Vercel-oriented Flask application using PostgreSQL and Vercel Blob Private Storage. The frontend remains static HTML/CSS/JavaScript. The project owner ran the complete v1.2.3 suite in WSL / Python 3.14: **10/10 tests passed in 2.557 seconds**, with no warning shown in the submitted terminal output. v1.2.3 includes Vercel edge/CDN security headers, function bundle exclusions, deployment configuration tests, dependency auditing in CI, and a corrected database-import/bootstrap runbook.

**The source-level test suite passes, but the project is not yet production-verified.** No live PostgreSQL connection, real Blob operation, GitHub repository creation, or Vercel deployment has been executed.

## Scope and deliverables

| Workstream | Deliverable | Status |
|---|---|---|
| Application adaptation | Flask entrypoint, `public/` static assets, Vercel configuration | Implemented; static checks pass |
| Database | PostgreSQL URL normalization, Flask-Migrate/Alembic, SQLite importer | Implemented; live DB not tested |
| Object storage | Local test adapter + Vercel Blob Private adapter | Implemented; real Blob not tested |
| Application security | Role checks, private file authorization, secure cookies, security headers, request/file size controls | Implemented; requires live smoke test and security review |
| Automated QA | Unit/integration tests, deployment config tests, GitHub Actions CI + `pip-audit` | Configured; final full run and hosted CI pending |
| Documentation | README, migration guidance, deployment runbook, project status | Prepared |
| Repository publication | New public repository under `shifi06` | Not started; publication remains on hold |
| Vercel resources | Project, Neon database, Private Blob | Not started; provisioning remains on hold |
| Deployment | Preview, smoke test, production | Explicitly on hold |

## Acceptance gates

### Gate A — Source readiness

- [x] Owner ran `python3 -m unittest discover -s tests -v` against v1.2.3: 10 tests PASS in 2.557 seconds; no warnings shown in the submitted output.
- [x] `vercel.json` parses and defines edge headers + function exclusions.
- [x] Python source compiles.
- [x] Frontend JavaScript syntax check passes.
- [x] `.gitignore` excludes secrets, local DBs, uploads, virtual environments, and Vercel local config.
- [ ] GitHub Actions CI and `pip-audit` are green after repository publication.

### Gate B — Infrastructure readiness

- [x] GitHub and Vercel connectors authenticate as `shifi06`; Vercel plan is Hobby.
- [ ] Create repository and Vercel project only after the publication/deployment hold is lifted.
- [ ] Neon PostgreSQL is provisioned for Tanding.in and separate from OLION.
- [ ] Runtime pooled and migration direct connection strings are configured.
- [ ] Vercel Blob store is created with **Private** access and connected to Tanding.in.
- [ ] `SECRET_KEY`, DB variables, storage selection, and one-time admin bootstrap variables are configured without committing secrets.

### Gate C — Live integration readiness

- [ ] Alembic migration succeeds against the target PostgreSQL instance.
- [ ] Role catalog and initial Super Admin bootstrap succeed.
- [ ] CRUD and authorization paths pass against PostgreSQL.
- [ ] Private Blob upload, authorized download, unauthorized denial, and delete succeed.
- [ ] Preview deployment passes HTTP/API smoke tests.

### Gate D — Production readiness

- [ ] Backup/restore procedure is documented and tested for the database.
- [ ] Monitoring/logging and incident contact are agreed by the owner.
- [ ] Known security gaps and operational limits are accepted or remediated.
- [ ] Project owner explicitly authorizes production deployment.

## Risk register

| ID | Risk | Impact | Mitigation / gate |
|---|---|---|---|
| R-01 | Publishing/provisioning remains on hold | No repository, project, database, or storage exists yet | Keep source package ready; wait for explicit go-ahead before creating resources |
| R-02 | No real PostgreSQL integration test yet | First runtime database calls could fail | Provision isolated Neon DB, migrate schema, run CRUD smoke tests |
| R-03 | Blob adapter has only fake-client coverage | Upload/download may fail due to credentials/store mode | Create a Private store and run live PUT/GET/DELETE tests |
| R-04 | Public GitHub repository | Source is visible to everyone | Keep secrets, `.env`, DB dumps, and uploaded evidence out of Git; run secret scanning |
| R-05 | Vercel Hobby terms/quotas | Service suspension or limits if used commercially or over quota | Restrict to personal/academic/non-commercial use and monitor quotas |
| R-06 | Account registration/login lacks a verified external anti-abuse/rate-limit control | Spam registration or brute-force attempts | Add/enable an appropriate rate-limit or bot-mitigation layer before broad public exposure |
| R-07 | Hobby/preview/production environment data separation | Test accounts could contaminate production | Use distinct Neon branch/database and Blob store strategy for preview vs production |

## Project governance decisions

- The friend's accounts own GitHub repository and Vercel resources.
- GitHub repository visibility is **public**.
- Vercel plan is **Hobby**; intended use must remain personal/academic/non-commercial and comply with current plan terms.
- Keep the Flask application architecture; do not rewrite to Next.js solely for deployment.
- Keep Tanding.in database and storage isolated from OLION.
- Publishing and deployment remain separate approval gates.

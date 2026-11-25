# JobHunter AI — Architecture

## 1. Requirements analysis (summary)

| Area | Decision |
|---|---|
| Users | Single owner account (multi-user-capable schema). JWT auth. |
| CV | PDF/DOCX upload → text extraction (pypdf / python-docx) → LLM structured extraction → **anti-hallucination guard** (every extracted skill/company must literally appear in the CV text) → heuristic fallback when no OpenAI key. Files encrypted at rest (Fernet). |
| Discovery | Only legitimate, ToS-respecting sources: **JSearch (RapidAPI)** and **SerpAPI Google Jobs**, which aggregate Google for Jobs (and through it LinkedIn, Indeed, Bayt, Naukrigulf, GulfTalent and company sites); **public ATS APIs** (Greenhouse, Lever, Ashby, Workable) for tracked companies; **schema.org `JobPosting` JSON-LD** on company career pages (robots.txt respected). We never scrape LinkedIn/Indeed directly and never bypass CAPTCHAs or anti-bot protections. |
| Company data | Enrichment from the company's *own* website: careers page, LinkedIn link, meta description, and recruitment emails that are **published on the company's own domain** and whose domain has MX records. No guessed addresses (`hr@domain` is never invented). |
| Dedup | Companies by domain → normalized name. Jobs by `source_url`, `(source, external_id)`, and a cross-board fingerprint (company + normalized title + city within 30 days). |
| Matching | LLM agent (score 0–100, matching/missing/transferable skills, explanation, recommendation) with a deterministic skill-taxonomy fallback. Category thresholds are computed by the backend (80/65/50), not by the LLM. |
| Emails | LLM writer fed **only** facts from the extracted CV, the job and the company. Post-generation check warns if the email mentions skills listed as missing. Every email is stored, versioned, editable, regenerable, approvable, rejectable. |
| Sending | Gmail API (OAuth 2.0, `gmail.send` + `gmail.readonly`), CV attached, message/thread ID stored. Sending requires an **approved** email; duplicates are blocked at DB (unique user+job) and service level (same company + same normalized title). |
| Online applications | "Form assist": opens the official application URL, detects form fields where the page is publicly fetchable, and gives pre-filled values from the approved CV for the user to paste. Final submission is always done by the user, who then confirms "Mark as applied". |
| Automation | APScheduler inside the API process runs the daily pipeline at the configured frequency; global pause switch; query budget per run; daily report. |
| Tracking | 11 statuses, full status history table, audit log, follow-ups, reply detection via Gmail threads. |
| Analytics | KPIs, per-day/week/city/category charts, response & interview rates, avg match score, CSV/XLSX export, daily "companies contacted today" report. |

## 2. System diagram

```
 Next.js dashboard (TS, Tailwind, shadcn/ui, Zustand, Recharts)
        │  REST + JWT
        ▼
 FastAPI ──► services/
   │          ├─ cv_parser        (pypdf, python-docx, LLM, guard)
   │          ├─ discovery/       (jsearch, serpapi, greenhouse, lever, ashby, workable, careers_page JSON-LD)
   │          ├─ enrichment       (company site → careers, LinkedIn, verified emails, MX)
   │          ├─ matching         (LLM agent + heuristic)
   │          ├─ email_writer     (LLM agent + guarded template)
   │          ├─ gmail_service    (OAuth, send w/ attachment, reply detection)
   │          ├─ applications     (status machine, history, duplicate guard)
   │          ├─ form_assist      (field detection + prefill, no auto-submit)
   │          ├─ pipeline         (daily 11-step workflow)  ◄── APScheduler
   │          ├─ analytics / reports / exports
   │          └─ audit
   ▼
 PostgreSQL (SQLAlchemy 2 + Alembic)       encrypted CV files on disk
```

## 3. Folder structure

```
jobs/
├─ ARCHITECTURE.md  README.md  docker-compose.yml
├─ backend/
│  ├─ .env.example  requirements.txt  alembic.ini  Dockerfile
│  ├─ alembic/ (env.py, versions/)
│  ├─ app/
│  │  ├─ main.py                 FastAPI app, CORS, lifespan (scheduler)
│  │  ├─ core/                   config, database, security (JWT/bcrypt), crypto (Fernet), logging
│  │  ├─ models/                 SQLAlchemy models (all tables)
│  │  ├─ schemas/                Pydantic request/response models
│  │  ├─ api/routes/             auth, cv, profile, companies, jobs, discovery, matches,
│  │  │                          applications, emails, gmail, followups, analytics,
│  │  │                          reports, exports, automation, audit
│  │  └─ services/               (see diagram) + skills taxonomy + keywords (EN/AR titles, cities)
│  ├─ scripts/                   create_user.py, run_pipeline.py
│  └─ tests/                     pytest (SQLite, external APIs mocked)
└─ frontend/
   ├─ package.json  tailwind.config.ts  components.json  .env.example
   └─ src/
      ├─ app/(auth)/login, app/(dashboard)/{overview, companies, jobs, matching, queue,
      │   sent, emails, followups, analytics, settings, profile}
      ├─ components/ui/          shadcn/ui primitives
      ├─ components/             sidebar, kpi-card, status-badge, filters, tables, charts
      └─ lib/                    api client, zustand stores, types, utils
```

## 4. Database tables

`users, candidate_profiles, candidate_skills, cvs, companies, jobs, job_requirements, job_matches,
applications, application_emails, email_history, follow_ups, search_history, daily_reports,
automation_settings` + supporting `application_status_history, audit_logs, automation_runs`.

All tables have integer PKs, FKs with `ON DELETE` rules, `created_at`/`updated_at`, and indexes on
lookup/filter columns (status, city, category, score, dates, domain, source_url).

## 5. Application status machine

`Discovered → Analyzed → Awaiting Approval → Approved → (email) Applied | (online) Ready to Apply → Applied
→ Follow-up Required → Response Received → Interview Scheduled → Rejected / Closed`

Manual updates may set any status; every change writes `application_status_history` and `audit_logs`.

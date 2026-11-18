# NL Career Tracker: project plan

A tracker for **jobs, internships and traineeships in the Netherlands**. It knows Dutch companies, checks each one against the **IND list of recognised sponsors**, compares each salary with the **IND salary thresholds**, analyses **your CV**, finds matching vacancies, and has a **Flutter mobile app (separate repo)**.

Status: planning only, nothing is built yet. Facts below were checked on **2026-11-18** against the pages listed in the Appendix. Anything marked **[verify]** was not confirmed and must be checked before you rely on it.

---

## 0. Read this first: three decisions that shape the plan

### 0.1 Your work-authorisation status changes everything

The tool must ask for it once (Profile screen) and then behave differently. I do not know your status, so the plan supports all of these:

| Status | What the tool does |
|---|---|
| EU / EEA / Swiss citizen | No permit needed. Sponsor badge and salary threshold are shown as "not required" and hidden by default. |
| Needs a permit and you (may) qualify for the **orientation year** (search year) | You can work freely for up to one year without a sponsor. The tool tracks the permit's end date and the **reduced salary threshold** that applies if you later apply within 3 years of graduating. |
| Needs a permit as a **highly skilled migrant** | The employer must be a **recognised sponsor** and the salary must meet the threshold for your age. This is the main use of the IND features. |
| Student on an internship | Internship rules apply [verify]. The IND table lists a lower "Internship" amount, but whether it applies to your case needs confirming. |

Whether the university you attend qualifies for the orientation year depends on the IND's list of designated foreign institutions [verify]. Do not assume it from this plan.

### 0.2 What this plan deliberately does NOT build

You asked for ways to fetch data from LinkedIn, Indeed and Glassdoor and to collect HR emails. I have planned **legal equivalents** instead and left out two things on purpose:

1. **No scraping of LinkedIn, Indeed or Glassdoor.** Their terms prohibit automated collection [verify the current terms of each]. LinkedIn has taken scrapers to court, and the realistic outcomes for you are an account ban and wasted work, since these sites change their pages and block bots. Section 4 gives routes that reach the same vacancies without breaking the rules: email alerts you subscribe to, "share to app" from your phone, and public job-board APIs.
2. **No harvesting of HR emails.** Collecting people's emails in bulk is processing personal data under the GDPR without a lawful basis, and the Dutch rules on unsolicited electronic messages (Telecommunicatiewet) may also apply [verify with the Autoriteit Persoonsgegevens or a lawyer; this is not legal advice]. It also works badly: scraped addresses are often wrong or outdated, bulk messages get filtered, and recruiters ignore them. Section 6 plans a **contact book** instead: contacts you found yourself, with where you found them, plus message drafts that **you** send.

If you later want to go further on either point, check the legal position first.

### 0.3 One rule for the whole project

Every number that comes from an outside source (IND amounts, register data, vacancy salary) is stored with its **source URL and date**, and the app shows it. A threshold without a date is a bug.

---

## 1. Goals and non-goals

### Goals

1. One place to track every job, internship and traineeship you consider, from "found" to "offer" or "rejected".
2. For every posting, show clearly: **is the employer an IND-recognised sponsor**, **does the salary meet the threshold for my status**, **does it need Dutch**, **how well does it match my CV and why**.
3. Analyse your CV once, then keep finding postings that fit it.
4. Work on your phone: triage new postings, get follow-up reminders, add a posting from your browser with one tap.
5. Be a good portfolio project: clean architecture, tests, measured accuracy, honest limits.

### Non-goals

- Applying for you. The app drafts, you send.
- Mass emailing or any automated outreach.
- Scraping sites whose terms forbid it.
- Legal or immigration advice. It shows what the IND publishes; you decide.

---

## 2. What the IND publishes (checked 2026-11-18)

### 2.1 Salary thresholds for 2026

From the IND page "Required amounts income requirements". Amounts are **gross per month, without holiday allowance**. The page says the highly skilled migrant and Blue Card amounts change every **1 January**.

| Category | Gross monthly amount |
|---|---|
| Highly skilled migrant, under 30 | EUR 4,357.00 |
| Highly skilled migrant, 30 or older | EUR 5,942.00 |
| Highly skilled migrant, **reduced criterion** (recent graduates / orientation year) | EUR 3,122.00 |
| EU Blue Card | EUR 5,942.00 |
| EU Blue Card, reduced criterion | EUR 4,754.00 |
| Internship (in the table of other categories) | EUR 1,168.50 |
| Paid employment, trainee and other categories | EUR 2,337.00 |

The "other categories" amounts on that page are marked valid **1 July to 31 December 2026**, so they change twice a year. The under-30 amount also applies if you turned 30 but changed employers while still under 30.

**Salary must also be "in line with the market rate"** (IND highly skilled migrant page). Meeting the number is necessary, not sufficient.

### 2.2 The register of recognised sponsors

- Only an employer **recognised by the IND** can apply for a highly skilled migrant permit for you.
- The register is on the IND website in four categories: **Work, Exchange, Study, Research**. This project needs **Work** (regular labour and highly skilled migrants).
- The Work page is **one HTML table with two columns: Organisation and KvK (Chamber of Commerce) number**, sorted alphabetically. The page text is very large (about half a million characters). One entry has no KvK number.
- It is **updated once a month**. The page showed "last updated 3 November 2026".
- No download file and no usage terms were visible [verify by opening the page and its footer].

### 2.3 The orientation year (summary, from government.nl and IND forms)

- Up to **one year** to look for skilled work, applied for by yourself, **no sponsor**, and you may **work freely** during it.
- Routes: a **Dutch** bachelor's, master's or post-master's (10+ months) completed within **3 years before applying**; or a master's/post-master's/PhD from a **designated foreign institution** (the "top university" route); other routes exist.
- A foreign diploma must be evaluated by **EP-Nuffic**. The 2026 application fee was **EUR 254**.
- If you later get a highly skilled migrant job, the **reduced salary criterion** applies if you apply **within 3 years of graduation**.
- The two sources differ slightly on the foreign-university wording, so check the IND's current list before relying on it.

---

## 3. Features

### 3.1 Dutch company directory

- **Seed from the IND register**: every recognised sponsor with a KvK number is a Dutch legal entity. That gives a first list of roughly all companies that can hire a migrant.
- Add your own: any company you care about, even if not in the register (the badge then says "not listed").
- Per company: name, KvK number, city, industry, careers-page URL, applicant-system type (Section 4.3), your notes, sponsor status and the date it was checked.

### 3.2 Sponsor check (compare with the IND list)

1. Download the Work register page once a month and parse the table into a **snapshot** (organisation, KvK, snapshot date). Keep old snapshots so you can see when a company appeared or disappeared.
2. Match a company to the register **by KvK number first** (exact), then by **normalised name** (lower case, strip "B.V.", "N.V.", punctuation) with fuzzy matching.
3. Show a badge: **Recognised** (date checked), **Not listed**, or **Unsure** (several fuzzy candidates, you pick one).
4. Show the caveats in the app:
   - Postings often name a **brand** ("Albert Heijn") while the register lists the **legal entity** ("Albert Heijn B.V." or the group). A fuzzy match needs your confirmation.
   - **Recognised does not mean it will sponsor you.** It only means it can.
   - The register changes monthly. An entry can be new or gone since you checked.

### 3.3 Salary check

For each posting with a salary, convert to the IND's unit and compare:

```
monthly_gross_excl_holiday = annual_gross_incl_holiday / 12.96     # assumes 8% holiday allowance [verify per posting]
monthly_gross_excl_holiday = monthly_gross_incl_holiday / 1.08
```

Pick the threshold from your profile (Section 0.1), then show a verdict:

| Verdict | Meaning |
|---|---|
| Meets | At or above the threshold, with the margin shown |
| Below | Under the threshold, with the gap shown |
| Unknown | The posting gives no salary. Show the threshold as "you need at least X" and an estimate if one exists. |

Rules:
- Thresholds live in a **versioned config file** with `valid_from`, `valid_to`, `source_url`, `checked_on`. The app warns when a threshold is past its `valid_to` or older than 6 months.
- Postings often give a range. Judge on the **lower end** and say so.
- Where a posting has no salary, an estimate from public salary data may be shown, **always labelled "estimate"** and never used for the Meets/Below verdict.

### 3.4 CV analysis

1. Upload your CV (PDF or DOCX) and extract the text.
2. Build a structured **profile**: skills, roles, education, languages with level, projects, years of experience, location and preferences (job vs internship, cities, remote, minimum salary, Dutch level).
3. Normalise skills against a skills taxonomy such as **ESCO**, the EU's multilingual skills and occupations list [verify its licence and data format].
4. Show you what the system understood and let you **correct it**. The profile is the source of truth, not the raw CV.
5. Show **gaps**: what the target postings ask for that your profile lacks, ranked by how often they appear.

### 3.5 Matching and fit score

A posting's fit is computed from separate, explainable parts:

| Part | How |
|---|---|
| Skills overlap | Weighted overlap between your skills and the posting's skills |
| Meaning similarity | Embedding similarity between your profile and the posting (Hugging Face `bge` embeddings, run locally) |
| Hard filters | Location, job type (internship vs job), Dutch required or not, seniority |
| Sponsor and salary | Shown beside the score, not mixed into it, so you can see them separately |

Every score comes with a written **reason** and the passages it was based on. **Evaluation (the data-science part):** label about 150 postings yourself as apply / maybe / skip, then measure the score against your labels. Compare three methods: skills overlap only, embeddings only, and the combination. Report precision at 10 and agreement, with the sample size.

### 3.6 Classifiers

| Classifier | Output | Notes |
|---|---|---|
| Job type | job / internship / traineeship / graduate programme | Dutch and English keywords as the baseline, a zero-shot Hugging Face model to beat it |
| Language required | English ok / Dutch required / Dutch a plus | The most useful filter for you. Evaluate on postings you label. |
| Seniority | intern / junior / medior / senior | Often missing; may be "unknown" |

### 3.7 Application tracker

States: `found → shortlisted → applied → screening → interview → offer → accepted`, plus `rejected`, `withdrawn`, `expired`. Each state change is logged with a date. Per application: documents sent (CV version), notes, follow-up date, contact, interview dates, and the sponsor and salary verdicts as they were **when you applied**.

### 3.8 Reminders

Follow up 7 days after applying; a posting closing soon; the monthly register refresh found a change for a company you track; your orientation-year permit end date approaching.

### 3.9 Insights

Applications per week, response rate by source and company type, time in each state, which skills the postings you like keep asking for. Honest numbers only: with few applications, show the count and say it is small.

---

## 4. Finding vacancies, legally

### 4.1 Sources and their status

| Source | How | Status |
|---|---|---|
| **Applicant-system public job boards** (Greenhouse, and others) | Public JSON endpoints | **Greenhouse: confirmed public.** The Job Board API says "authentication is not required for any GET endpoints" and returns title, location, link, content, and pay ranges where the company publishes them. Check each other system (Lever, Ashby, Workable, Recruitee, SmartRecruiters) before use **[verify]**. |
| **Adzuna API** | Official REST API with an app id and key | Netherlands reported as supported (country code `nl`) by third-party listings, but the official page I read did not list countries, limits or storage terms **[verify the official terms before storing results]** |
| **Company career pages** | Fetch the page the company publishes for applicants | Allowed only if the site's `robots.txt` and terms allow it. Respect them, rate-limit, cache. **[verify per site]** |
| **Dutch government and university vacancy pages** | Often have public feeds or open pages | **[verify]** per site |
| **LinkedIn, Indeed, Glassdoor email alerts** | You create alerts in each service; the tool **reads the alert emails you receive** (your own mailbox, by IMAP or by forwarding to a dedicated address), then looks the company up on its own site (Sections 4.4 and 4.5) | Fine: it is your own data from a feature those services provide. Parsing layouts may break; expect maintenance. |
| **Share from phone** | On any posting, tap Share and choose the app; it receives the URL or the text you selected | Fine for a page you opened yourself, one at a time. For sites that forbid automated access, prefer sharing **the text** you copied over fetching the page. |
| **Manual paste** | Paste the posting text; the tool parses it | Always works |

Not planned: automated crawling of LinkedIn, Indeed or Glassdoor, and unofficial or reverse-engineered APIs of those sites.

### 4.2 Discovery pipeline

```
sources -> fetch (polite) -> parse -> normalise -> dedupe -> enrich -> score -> store -> notify
```

0. **Alerts**: read new alert emails (4.4); for each company, run the web-resolution layer (4.5).
1. **Fetch**: one adapter per source behind a `JobSource` port. Rate limit, a clear user agent, caching, and exponential backoff. Obey `robots.txt`.
2. **Normalise** into one schema (Section 7): title, company, location, type, language, salary range with its unit, posted date, URL, source, raw text.
3. **Dedupe**: same company and similar title and city within a window; confirm with embedding similarity. The same job on three boards is one job.
4. **Enrich**: link to a company, run the sponsor check and the salary check, run the classifiers.
5. **Score** against your profile and store the reason.
6. **Freshness**: re-check stored postings; mark `expired` on 404 or a "closed" page. (career-ops, a similar open-source tool, notes that expired postings can linger; build the check in from the start.)
7. **Report** after every run: sources that worked, sources that failed, new postings. A silent failure is worse than a loud one.

### 4.3 Turning the register into a vacancy source

The IND register gives a list of Dutch employers that can sponsor. For each one, the company web-resolution layer (Section 4.5) finds the website, the careers page and the applicant system, so the register becomes a source of vacancies without touching sites that forbid it. Expect many companies to need manual configuration, and some to publish nothing usable.

### 4.4 Alert-email reader (the entry point)

Job-alert emails you receive from LinkedIn, Indeed and Glassdoor are the **trigger**: they tell the app which company is hiring for which title, and the layers below find the full posting on the company's own site.

- **How the mail arrives:** a dedicated mailbox or label that you control, read over IMAP with an app-specific password or an OAuth token (never your main password) **[verify the provider's current method]**; or you forward alerts to an address the app owns.
- **Alert setup (done by you, once):** one saved search per title on each site, location Netherlands, "date posted: past 24 hours" where offered, **daily** email frequency. Suggested titles to start: your target roles plus "intern" / "stagiair" / "traineeship" variants.
- **Parser:** one small parser **per sender and email layout** behind an `AlertEmailParser` port. Each extracts `title`, `company`, `location`, `posting_url`, `received_at` and any snippet the email contains. Unknown layouts are saved untouched in a "needs a parser" list, never dropped silently.
- **Tracking links:** alert links contain tracking parameters. Strip them before storing, and do **not** follow them automatically (they would also act as a click for you on the site).
- **What the first pass can do with only title, company and city:** classify job type and likely seniority, run the sponsor check, drop obvious mismatches (wrong city, wrong field) and queue the company for the next layer.
- **Limit:** the email has no full description and rarely a salary. That is the reason for the layer below.

### 4.5 Company web-resolution layer (the "search layer")

**Goal:** from a company name in an alert, find the company's website and careers page, find the same vacancy there, and extract the full posting. This layer works on **companies' own sites**, not on LinkedIn, Indeed or Glassdoor.

```
alert (company, title, city)
  1. company cache         -> known website and careers page? use them, skip to 5
  2. resolve the website   -> candidates, scored, confirmed
  3. find the careers page -> links, common paths, sitemap
  4. detect the system     -> public board API? structured data? plain HTML?
  5. extract postings      -> best method first, fall back step by step
  6. match to the alert    -> same title and city?
  7. enrich and store      -> salary, language, classifiers, sponsor, fit, source URL
```

**Step 2: resolve the website.** Try in this order and stop at the first confident result:

| Order | Source | Notes |
|---|---|---|
| a | Your cache and your confirmed list | Free and always right |
| b | Wikidata "official website" for notable companies | Open data **[verify coverage and licence]** |
| c | An **official search API** with a query like `"<company>" official website Netherlands` | Provider, price and terms **[verify]**. **Do not scrape the result pages of Google, Bing or DuckDuckGo**; their terms forbid it. |
| d | Guessed domains (`name.nl`, `name.com`, name without "B.V.") | Always verified by fetching the homepage |

Score each candidate by: the company name in the page title, Dutch or English text, and above all **the KvK number**. Dutch businesses normally have to show their KvK number on their website **[verify the rule]**. If the number on the site equals a number in the IND register, you have confirmed **both the website and the legal entity**, and the sponsor check becomes exact instead of fuzzy. That is the strongest signal in the whole design.

Confidence levels: **high** (KvK matches), **medium** (name and country match, no KvK found), **low** (a guess). Low confidence is shown to you in the app ("Is this the right site?") and nothing is extracted until you confirm. Name collisions are common, so wrong-company data is the main risk of this layer.

**Step 3: find the careers page.**
- Read the homepage links and footer for these words (English and Dutch): `careers`, `jobs`, `vacancies`, `vacatures`, `werken bij`, `werkenbij`, `join us`, `solliciteren`, `stage`, `traineeship`.
- Try common paths: `/careers`, `/jobs`, `/vacatures`, `/werken-bij`.
- Dutch companies often use a separate address such as `werkenbij.<company>.nl` **[verify per company]**.
- Check `sitemap.xml` for job URLs.
- Always read `robots.txt` first and skip anything it disallows.

**Step 4: detect the applicant system** from link patterns, embedded frames and scripts (Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters, Teamtailor, Personio, Workday and similar). Greenhouse's public board API is **confirmed**; for every other system confirm whether a public interface exists **[verify]** before using it.

**Step 5: extract the posting, best method first.**

| Priority | Method | Why |
|---|---|---|
| 1 | A **public job-board API** of the applicant system | Structured, stable, meant for outside use (where confirmed) |
| 2 | **schema.org `JobPosting` structured data** (JSON-LD) in the posting page | Many sites publish it for Google; it can carry title, description, `datePosted`, `validThrough`, employment type, location and salary **[verify on real pages; not every site has it]** |
| 3 | Job URLs from the sitemap, parsed with generic HTML rules | Works on simple sites |
| 4 | A Hugging Face model extracts fields from the page text | Last resort. Every field gets a confidence value and the raw text is saved. |

A field that cannot be found stays **empty**; it is never guessed. Salary and dates are never invented.

**Step 6: match the alert to the posting.** Compare titles (fuzzy text plus embedding similarity) and the city. One clear match: link them. Several: show the best three to you. None: mark "not found on the company's site", which is useful information (the vacancy may be closed, or posted somewhere else).

**Step 7: enrich and store** with the **source URL and fetch date**: salary normalisation and verdict, language and job-type classifiers, sponsor status, fit score and reason.

**Rules for this layer**
- `robots.txt` is honoured; a clear user agent that names the project and gives a contact address; at most **one request per second per host**; cache with `ETag` / `Last-Modified`; a cap on pages per company per run; stop at once on a 403 or 429 and mark the company "blocked" for a while.
- A company's own careers page is published for applicants, but its terms can still restrict automated reading **[verify per site; check the footer]**. When a site forbids it, the app shows "open in browser / share to app" instead.
- Data extracted is **about the vacancy and the company only**. Do not extract recruiter names or emails from pages automatically; use the contact book (Section 6).
- Everything is cached per company, so the search happens once, not on every alert.

**Evaluation (hand-check 100 companies):** website resolution accuracy (top-1), share of companies where a careers page was found, extraction success per method (1 to 4), alert-to-posting match accuracy, and how often step 2 confirmed a KvK number. Report each method separately.

## 5. Using the data you already hold

The IND register is a **cold list of employers**. Combine it with:

- Your target **industries and cities**: filter the register by city only if you add a company's address from the company's own site or a public registry **[verify which registry and its terms, for example the Chamber of Commerce (KvK) open data]**.
- Your **own history**: companies you have applied to or heard back from.

Do not buy or scrape contact lists.

---

## 6. Contacts: a contact book, not an email harvester

### 6.1 What it stores

A contact is someone **you** found or met, with: name, company, role, where you found them (URL or event), the date, how you are connected, last interaction, next step, and a field for consent or opt-out ("asked not to be contacted").

### 6.2 Where contacts can legitimately come from

- The **company's own careers or contact page** that invites applicants to write to a general address (for example a generic recruiting mailbox). Store the address as published, with the URL and date.
- People you **met** at a career fair, meetup, webinar or through your university, who gave you contact details.
- Recruiters who **wrote to you**.
- Alumni you contact through the platform's own messaging (for example a LinkedIn message you write yourself), not by exporting emails.

### 6.3 Outreach rules built into the app

- The app **drafts** a short, personal message (Hugging Face model, using your profile and the posting). **You read, edit and send it yourself** from your own email.
- No bulk send. No scheduled automated sequences.
- One follow-up at most; after that the contact moves to "closed".
- A **retention rule**: contacts you never interacted with are deleted after 12 months [decide your own period]. A **delete contact** button erases everything about someone.
- Do not store personal data you do not need.

---

## 7. Data model

```
Profile(id, work_status, birth_date_or_age_band, graduation_date, languages, preferences, min_salary)
Document(id, type[cv|cover|other], version, text, uploaded_at)
SponsorSnapshot(id, snapshot_date, category[work], source_url)
SponsorEntry(snapshot_id, organisation, kvk_number)
Company(id, name, kvk_number, city, industry, website, careers_url, ats_type,
        sponsor_status[recognised|not_listed|unsure], sponsor_checked_on, notes)
CompanyWebProfile(company_id, website, careers_url, ats_type, resolution_confidence[high|medium|low],
                  kvk_on_site, resolved_at, last_crawled_at, blocked_until, confirmed_by_user)
AlertEmail(id, sender, received_at, parser, raw_ref, parsed_ok)
Job(id, source,  source_job_id, url, company_id, title, location, type, language_required,
    seniority, salary_min, salary_max, salary_period, salary_basis[stated|estimated],
    posted_at, last_seen_at, status[open|expired], raw_text, fit_score, fit_reason,
    salary_verdict, threshold_used)
Application(id, job_id, state, applied_at, document_id, follow_up_at, notes)
ApplicationEvent(id, application_id, from_state, to_state, at, note)
Contact(id, company_id, name, role, source_url, found_on, connection, last_contact_at, next_step, do_not_contact)
Interaction(id, contact_id, application_id, kind, at, summary)
Threshold(id, category, amount_eur_month, valid_from, valid_to, source_url, checked_on)
SourceRun(id, source, started_at, finished_at, ok, new_jobs, error)
Reminder(id, kind, due_at, target_id, done)
```

Salary values keep their original period and a normalised monthly amount, so nothing is silently converted.

---

## 8. Architecture

Same style as project 01: **feature folders with clean-architecture layers**, so you can explain and defend the structure.

```
backend/careers/
  features/
    sponsors/      domain: matching rules | application: RefreshRegister, CheckCompany | infrastructure: IND page parser, SQL | api
    thresholds/    domain: salary normalisation, verdict rules | infrastructure: config loader | api
    profile/       domain: profile model | application: AnalyseCv | infrastructure: PDF/DOCX reader, skills extractor | api
    jobs/          domain: dedupe, normalisation | application: Discover, Rescore | infrastructure: source adapters | api
    alerts/        domain: alert model | application: ReadAlerts | infrastructure: IMAP reader, one parser per sender | api
    companyweb/    domain: candidate scoring, title matching | application: ResolveCompany, FindPostings | infrastructure: search API client, robots.txt reader, page fetcher, JSON-LD and HTML extractors | api
    applications/  domain: state machine | application: Track, Remind | api
    contacts/      domain: retention rules | api
    assistant/     RAG over your documents, MCP tools (Section 10)
  pipeline/        composition roots: refresh_register, discover_jobs, score_jobs
  api/app.py       composition root for the web side
  tests/           including an architecture test that enforces the layer rules
```

| Part | Technology |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, pydantic-settings |
| Database | PostgreSQL 16 with pgvector for embeddings (SQLite for quick local tests) |
| Embeddings and classifiers | Hugging Face models run locally: a `bge` embedding model, plus a zero-shot or fine-tuned classifier |
| Parsing | `pypdf` or similar for PDF, `python-docx` for DOCX, `beautifulsoup4` or `lxml` for HTML **[verify the exact packages]** |
| Scheduling | A cron job or APScheduler first; Dagster later if you want a named orchestration tool |
| Container | Docker Compose: API, database, scheduler |
| Tests and lint | pytest, ruff, an architecture test, a CI workflow |
| Docs | A generated API reference (the script from project 01 can be reused) and a build journal in the same style |

Ports (interfaces) to define early: `JobSource`, `SponsorRegisterSource`, `AlertEmailParser`, `CompanyWebResolver`, `CareerPageFinder`, `JobPageExtractor`, `RobotsPolicy`, `Embedder`, `Classifier`, `CvReader`, `NotificationSender`. Swapping a model or a source then touches one adapter.

---

## 9. Flutter mobile app

### 9.1 Screens

| Screen | Content |
|---|---|
| **Today** | Follow-ups due, postings closing soon, new strong matches, a register-change alert |
| **Discover** | New postings as cards. Swipe right to shortlist, left to skip. Each card shows the **fit score**, a **Recognised sponsor** badge, and the **salary verdict**. |
| **Job detail** | Full posting, why it matched (with the CV passages used), sponsor and salary panels with source and date, "Add to pipeline", "Open original" |
| **Pipeline** | Kanban board by state; drag to move; tap for notes and dates |
| **Companies** | List with sponsor badge and your notes |
| **Contacts** | Your contact book with last interaction and next step |
| **CV and profile** | What the system understood from your CV, editable; work status and preferences |
| **Insights** | The numbers from Section 3.8 |
| **Settings** | Work status, notification times, server address, theme (light, dark, auto), biometric lock, data export and delete |

### 9.2 Mobile-only features

- **Share sheet**: share a posting URL or text from any browser or app straight into the tracker (the main way to capture LinkedIn, Indeed and Glassdoor postings you view yourself).
- **Push notifications** for follow-ups and new matches (a push service such as Firebase Cloud Messaging **[verify the setup and costs]**), plus local notifications that work offline.
- **Offline-first**: the pipeline and notes are stored on the phone and synced when online.
- **Biometric lock**: CV and contact data are personal.
- **Deep links** from notifications to the relevant job.
- **Home-screen widget** with the number of follow-ups due (later).
- **Document scan** with the camera for a job-fair flyer or business card, to create a contact (later; Hugging Face OCR).

### 9.3 App architecture

Clean architecture per feature, matching the backend: `data` (API client, local database), `domain` (entities, use cases), `presentation` (screens, state). Candidate packages, **none verified for current versions**: Riverpod (state), go_router (navigation), dio (HTTP), drift or isar (local database), flutter_local_notifications, firebase_messaging, receive_sharing_intent, local_auth. Test at three levels: unit tests for use cases, widget tests for screens, one integration test for the main flow.

### 9.4 How the app talks to the backend

A small REST API with a **single-user token** (you are the only user). The server stays on your machine or a home server at first. If you deploy it, add proper authentication and HTTPS **before** exposing it. The app never talks to job sites itself; only the backend does, so rules and rate limits are enforced in one place.

---

## 10. Assistant: RAG and MCP

This is the AI-engineering showpiece, built after the tracker works.

- **RAG over your own documents**: your CV, cover-letter drafts, notes, the postings you saved. A question like "which of my projects best matches this posting?" returns an answer with citations to your own text. Reuse the retrieval and evaluation approach from project 01.
- **Multiple knowledge sources** with a router that picks where to look: your documents, the stored postings, and the IND and threshold facts (answered from the database, not from model memory). Measure routing accuracy.
- **An MCP server** that exposes tools: `search_jobs`, `check_sponsor(company)`, `salary_check(salary, status)`, `list_pipeline`, `add_application`, `draft_message(job, contact)`. Any MCP client or agent can then use the tracker. Keep the tool set small and well described; measure token cost per question.
- **Models**: Hugging Face. Use local models for anything touching your CV; use a hosted model only for non-personal text, and say so.
- **Refusals**: when the sources do not cover a question, the assistant says so. Salary thresholds and sponsor status are **never answered from memory**, only from the stored, dated records.

---

## 11. Privacy and security

- Your CV, contacts and application history are personal data. Default to **local-first**: the database stays on your machine or a server you control.
- Run CV analysis with **local models**. If you ever send text to a hosted model, show a visible notice first.
- Encrypt backups. Keep secrets in `.env`, never in the repository. Add `.env`, the database and uploaded documents to `.gitignore`.
- Contacts: data minimisation, a retention period, a delete button (Section 6.3).
- Every outside request identifies itself honestly, rate-limits itself, and respects `robots.txt`.
- No credentials for LinkedIn, Indeed or Glassdoor are ever stored by this app.

---

## 12. Roadmap (phases, each with a "done when")

**Phase 0: Feasibility checks.** Open each planned source's terms and `robots.txt`; fetch the IND Work register once and confirm it parses; confirm which applicant systems have public JSON; confirm Adzuna's official terms and the `nl` country; decide the work-status profile. *Done when:* a one-page table of sources marked allowed or not, and a script that turns the register page into 2 columns of data.

**Phase 1: Core tracker and IND features (web or API only).** Sponsor snapshot and matching, thresholds config and salary verdicts, company directory, manual job entry, application tracker with states, tests, CI, Docker. *Done when:* you can add a posting by hand and see sponsor and salary verdicts with sources and dates; sponsor matching checked by hand on 100 companies with the precision reported.

**Phase 2: CV analysis and matching.** CV reader, profile extraction and correction, classifiers, fit score with reasons, your 150 labelled postings, the comparison table. *Done when:* the evaluation table exists and you can state what the score is worth.

**Phase 3: Legal discovery.** Alert-email reader with parsers, the company web-resolution layer (website, careers page, extraction, matching), Greenhouse and Adzuna adapters, dedupe, freshness checks, run reports. *Done when:* a scheduled run turns a day's alert emails into full postings where the company publishes them, and reports which companies or sources failed and why.

**Phase 4: Flutter app.** Pipeline, Discover, Job detail, Today, share sheet, local notifications, offline sync, biometric lock. *Done when:* you can capture a posting from your phone, triage it, and receive a follow-up reminder.

**Phase 5: Assistant.** RAG with citations, router, MCP server, evaluation set. *Done when:* a question set shows retrieval and routing scores and the refusal test passes.

**Phase 6: Polish and publish.** Push notifications, contact book, insights, generated API docs, build journal, deployment with real authentication, a short demo using sample (not personal) data. *Done when:* a reviewer can run it with one command and see a demo that contains none of your personal data.

---

## 13. How to know it works (metrics)

| Area | Measure |
|---|---|
| Sponsor matching | Precision and recall on 100 hand-checked companies; share needing manual confirmation |
| Salary parsing | Accuracy on 100 hand-checked postings (period, currency, holiday allowance) |
| Fit score | Precision at 10 and agreement with your labels; compared with the two simpler methods |
| Classifiers | Per-class precision, recall and F1, with the confusion matrix |
| Company web resolution | Website top-1 accuracy, careers-page found rate, extraction success per method, alert-to-posting match accuracy (100 hand-checked companies) |
| Dedupe | Duplicate rate before and after |
| Sources | Success rate per run; freshness (share of stored postings still open) |
| Assistant | Retrieval hit rate, routing accuracy, answer correctness, refusal rate |
| App | Time from "see a posting" to "in the pipeline" |

---

## 14. Risks and open questions

| Risk | Plan |
|---|---|
| A source forbids automated access | Do not use it; use alerts, share or paste instead |
| Wrong website for a company with a common name | Score candidates, prefer a matching KvK number, ask you to confirm low-confidence ones |
| A company site forbids automated reading | Honour `robots.txt`; fall back to share-to-app |
| Register layout changes | Parser test against a saved copy; alert when parsing fails |
| Brand vs legal entity mismatch | Match by KvK; ask you to confirm fuzzy matches |
| Thresholds go stale | Dates in config; warnings; yearly update task |
| Few labelled examples | State the sample size; never over-claim |
| Scope creep | Phases above; each phase useful on its own |
| Legal questions on outreach | Contact book and manual sending only; get advice before anything more |

**Questions to answer before building:**
1. Your work-authorisation status, and your graduation date and university (decides which thresholds and rules apply).
2. Jobs, internships, or both? Target cities and role families?
3. Your Dutch level (decides how much the language filter matters).
4. Where will it run: your laptop only, or a small server?
5. Android, iOS, or both?
6. Should the contact book exist at all in the first version, or wait?
7. Which search API for step 2 of the web-resolution layer (cost and terms to check), or start with Wikidata and guessed domains only?

---

## Appendix: sources checked on 2026-11-18

- IND, required amounts (income requirements): https://ind.nl/en/required-amounts-income-requirements (2026 highly skilled migrant, Blue Card and other amounts)
- IND, highly skilled migrant: https://ind.nl/en/residence-permits/work/highly-skilled-migrant (employer must be recognised; salary in line with market rate)
- IND, public register of recognised sponsors: https://ind.nl/en/public-register-recognised-sponsors (monthly updates; four categories)
- IND, register for regular labour and highly skilled migrants: https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants (two columns: organisation and KvK number; last updated 3 Nov 2026 when read)
- Government of the Netherlands, orientation year: https://www.government.nl/topics/immigration-to-the-netherlands/options-for-entrepreneurs-and-employees-from-abroad/orientation-year-highly-educated-persons (summary read through a search result; the IND page itself was not reachable at the address I tried)
- Greenhouse Job Board API: https://docs.greenhouse.io/job-board.html (public GET endpoints, no authentication)
- Adzuna API overview: https://developer.adzuna.com/overview (the official page did not state countries, limits or storage terms)
- career-ops (similar open-source project): https://github.com/career-ops-hq/career-ops (read only the README; statistics on that page are self-reported)

**Not verified, so treat as open:** LinkedIn, Indeed and Glassdoor current terms; Lever, Ashby, Workable, Recruitee and SmartRecruiters public APIs; Adzuna's official country list, limits and storage terms; whether your university is on the IND's designated list; the internship rules for your status; ESCO licence and format; Dutch rules on unsolicited messages; Flutter package versions; push-notification setup and costs.

# Data sources, licences and crawling etiquette

Read this before hosting a public instance.

| Source | Used for | Terms |
|---|---|---|
| Company career pages / public ATS APIs (Greenhouse, Lever, Ashby, Recruitee, SmartRecruiters, Workable, Teamtailor, Personio, BambooHR, Homerun, Workday) | job postings | Public endpoints intended for job-board embedding. Postings link back to the employer's own page. Respect each site's terms. |
| IND register of recognised sponsors (ind.nl) | "recognised sponsor" badge | Public register. Informational only, **not legal advice**; always verify at ind.nl. |
| Wikidata | company names, websites | CC0 |
| Wikipedia | company categories/websites | CC BY-SA 4.0 (attribute if you republish) |
| OpenStreetMap (Overpass) | company names/cities/websites | ODbL — **© OpenStreetMap contributors**; attribution required on public instances |
| europeantechmap.eu | company names/websites (read from public pages) | Check their terms before republishing the list; the app only stores names + websites |
| Company homepages | logo, meta description | Logos are trademarks of their owners and are shown only to identify the employer |

## Not used, on purpose
LinkedIn, Indeed, Glassdoor, search-engine result pages, job aggregators (they host duplicate/stale listings and force applications through them).

## Crawling etiquette (enforced in code)
- `robots.txt` honoured for every careers page; per-host rate limit (1 req/s, 0.2 s for ATS APIs).
- User-Agent identifies the project and a contact (`CAREERS_CONTACT`). **Set it to your own URL/e-mail.**
- Dead ends back off exponentially instead of being re-crawled.
- If a site owner asks you to stop, remove the company (`DELETE /api/companies/{id}`) and add it to a block-list.

## Personal data
The server stores no visitor data. Profile and pipeline notes are personal and are **never exposed** on a public instance (admin only). Do not commit `careers.db`.

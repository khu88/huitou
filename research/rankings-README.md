# CORE / TH-CPL comparison snapshot

This data supplements the CCF catalog. The systems have different purposes and
versions; grades are not translated or inferred from one system to another.

## Official sources

- CORE / ICORE: [official portal](https://portal.core.edu.au/conf-ranks/), source
  **ICORE2026**, downloaded 2026-10-28 using its public **Export** action.
  [Exact export URL](https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=atitle&page=1&do=Export).
  `sources/core-icore2026.csv` preserves all 987 rows: 825 letter-ranked venues
  and 162 other entries. The headerless CSV columns are source record ID,
  title, acronym, version, rank/status, DBLP indicator, and three field-of-research
  codes. Statuses such as `Multiconference`, `Journal Published`, `Unranked`,
  and `National: USA` are preserved as source text, not converted to grades.
- TH-CPL: [Tsinghua-hosted original PDF](https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf),
  whose cover states approval on **2019-08-13**. This is a versioned historical
  source, **not a claim that the PDF is the latest TH-CPL**. The 17-page PDF is
  saved as `sources/th-cpl-2019-08-13.pdf`. Only the conference tables are
  extracted: 77 A entries and 148 B entries; all journal tables are excluded.
  The adjacent `.txt` and `-conferences.json` contain layout extraction and
  conference rows with one-based page numbers.

`conference-rankings.json` contains the source URLs, SHA-256 digests, versions,
review date, coverage counts and one entry for each of the 390 catalog IDs.

## Matching and uncertainty

1. Match a unique normalized full title, ignoring case, punctuation and `&/and`.
2. For differing titles, use only a manually reviewed mapping in
   `ranking-matches-reviewed.json`, which records both titles, source acronym,
   source ID and rationale. No fuzzy similarity or acronym-only match assigns a
   grade at build time. A source-title or catalog-title change makes a reviewed
   mapping fail rather than silently reusing it.
3. No reliable match results in `rank: null, status: unconfirmed`. This means
   the mapping has not been confirmed; it does not mean the venue is unranked or
   absent from the official system.
4. A matching CORE row with a non-letter status uses `rank: null,
   status: listed-unranked` and keeps the exact `sourceRank`. This internal status
   covers the portal's different non-letter categories; show `sourceRank` to
   users rather than implying that all categories mean the same thing.

Collision cases were reviewed explicitly: software-engineering FSE (CORE 52)
versus Fast Software Encryption (1475); Edge Computing SEC (2246) versus IFIP
security SEC (804); semantic-web ISWC (1338) versus wearable-computers ISWC
(708); International Test Conference ITC (710) versus Teletraffic ITC (2214);
Interaction Design and Children IDC (851) versus Intelligent Distributed
Computing IDC (2203). The CCF WISA title does not match CORE's security WISA,
so its CORE value stays unconfirmed.

TH-CPL's ICWS entry is explicitly **Research Track**; this scope is preserved.
The combined CADE/IJCAR row is annotated for CADE. Sources retaining the old
USENIX ATC name are marked as historical names when displayed for the current
CCF ACM SIGOPS ATC entry.

## Rebuild locally

No network access or additional package is needed for a normal rebuild:

```sh
python3 scripts/build_rankings.py
python3 scripts/build_data.py
python3 scripts/validate_data.py
```

To repeat PDF extraction, use an **existing** Python environment with `pypdf`:

```sh
python3 scripts/build_rankings.py --extract-thcpl
```

The extractor asserts 17 pages and 77 A / 148 B conference records. Sources
are not refreshed automatically; updating a source/version requires a new
snapshot and review of the mappings. Ordinary app startup and use make no
requests to the ranking websites.

## UI contract

`conference.rankings.core` and `.thcpl` each have `rank`, `status`, `version`,
`source`, `sourceLabel`, `verifiedAt` and `note`. Matched entries additionally
have `sourceTitle`, `sourceAcronym`, `sourceRecordId`, `sourceRank`,
`matchMethod` and `matchNote`; TH-CPL also has `sourcePage` and `sourceArea`.
The catalog root has `rankingSources`, `rankingCoverage` and
`rankingMatchingPolicy`. CORE matched entries link to the official record;
TH-CPL entries link to the original PDF and expose a one-based page number.

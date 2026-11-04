# Architecture Decisions

This document records the key technical decisions made in this project, the alternatives considered, and the reasoning behind each choice.

---

## 001 · Storage: DuckDB

**Decision:** Use DuckDB as the analytical database.

**Alternatives considered:** BigQuery (free tier).

**Reasoning:**
- Runs locally as a single file, with no cloud account or credentials needed.
- Anyone can clone the repository and run the full pipeline in minutes.
- dbt supports it through the `dbt-duckdb` adapter.

**Trade-offs:** It is not a distributed cloud warehouse, so it would not scale to very large datasets. A BigQuery target may be added later to show portability.

---

## 002 · Data sources: Madrid air quality + Open-Meteo

**Decision:** Combine two sources: Madrid City Council air quality data and Open-Meteo weather data.

**Alternatives considered:** EMT / BiciMAD (requires registration), the GitHub API (more generic, less original), and the City Council's own meteorological stations instead of Open-Meteo (real measurements, but not every air quality station has one, and the project would lose the REST API extraction component).

**Reasoning:**
- Two sources allow answering a real business question: how does weather affect air pollution in Madrid?
- Combining them forces solving real-world problems: joins across sources, time zones and incremental loads.

**Trade-offs:** Harder to integrate: different formats, different time granularity, and measurement stations vs geographic coordinates.

---

## 003 · Orchestrator: Airflow

**Decision:** Use Apache Airflow as the orchestrator.

**Alternatives considered:** Dagster.

**Reasoning:**
- Airflow is the industry standard and the most requested orchestrator in data engineering job postings.

**Trade-offs:** Heavier local setup (several services in Docker, more RAM). Task-based model, while Dagster's asset-based model integrates more naturally with dbt.

---

## 004 · Development environment: WSL2

**Decision:** Develop inside WSL2 (Ubuntu) on Windows.

**Alternatives considered:** Docker only from Windows, or a Linux virtual machine / dual boot.

**Reasoning:**
- Airflow only runs on POSIX-compliant systems.
- A Linux development environment mirrors production, which almost always runs on Linux.

**Trade-offs:** Learning curve, two separate file systems (working under `/mnt/c` is slow) and extra RAM usage.

---

## 005 · Python tooling: uv + Python 3.12

**Decision:** Use uv to manage the Python version, virtual environment and dependencies, pinned to Python 3.12.

**Alternatives considered:** `venv` + `pip`, and Python 3.14 (the Ubuntu system version).

**Reasoning:**
- uv is much faster and generates a lock file (`uv.lock`) with exact versions, so anyone can reproduce the same environment with `uv sync`.
- Python 3.12 is supported with margin by the whole stack (dbt, the DuckDB adapter and Airflow). Python 3.14 is only supported by the very latest dbt versions.

**Trade-offs:** Airflow only officially supports pip installations. The impact is low because Airflow will run in its official Docker image. Python 3.12 misses newer language features.

---

## 006 · Historical scope: from 2024

**Decision:** Load data from 2024-01-01 onwards.

**Alternatives considered:** From 2019 (start of municipal meteorological data, includes the 2020 lockdown anomaly).

**Reasoning:**
- More than one full year is needed to capture seasonal patterns.
- Keeps data volume small for fast local development.
- The start date is a parameter, so the range can be extended without code changes.

**Trade-offs:** The 2020 lockdown, a very interesting anomaly, is out of scope by default.

---

## 007 · Madrid ingestion method: files instead of the CKAN API

**Decision:** Download the yearly historical CSV files plus the real-time CSV file.

**Alternatives considered:** The CKAN `datastore_search` API.

**Reasoning:**
- Files are simple and robust, and the original file can be stored untouched in the raw layer.
- Any transformation can be reprocessed without downloading data again.
- The project already includes a REST API source (Open-Meteo).

**Trade-offs:** Whole files are downloaded even when only recent rows are needed.

---

## 008 · Time handling: UTC and period-ending convention

**Decision:** Store all timestamps in UTC. Hourly values are labeled with the end of their measurement period.

**Reasoning:**
- Madrid data is published in local time (UTC+1/UTC+2). Local time is ambiguous during the October DST change and has a missing hour in March.
- According to the source documentation, `H24` is the average from 23:00 to 24:00, so `Hn` covers the hour ending at `n`. `H24` maps to 00:00 of the next day.
- Open-Meteo accumulated variables also refer to the preceding hour, so both sources align naturally.

**Trade-offs:** DST transition days require explicit handling, and timestamps must be converted back to local time for display.

---

## 009 · Data validity and missing values

**Decision:** Only values flagged `V` are considered valid. Values flagged `N` are loaded as NULL. Missing values are never imputed.

**Reasoning:**
- The source documentation does not define the validation flags. The interpretation is inferred from the data: hours that had not occurred yet appeared as `0` with flag `N`.
- Loading those zeros as real values would silently bias averages downwards.
- A data test will assert that only `V` and `N` exist, so any new flag fails loudly.

**Trade-offs:** The interpretation relies on observation rather than official documentation.

---

## 010 · Resource discovery through CKAN metadata

**Decision:** Discover download URLs at runtime with the CKAN `package_show` API instead of hardcoding them.

**Reasoning:**
- The portal reorganised its resources during development: a yearly URL found early on stopped existing.
- Resources are identified by their `hierarchy_name` field ("2024", "Desde 2025"), parsed with a regular expression. Resource IDs do not follow year order.
- The extraction fails loudly if a required year is missing or no open period is found.

**Trade-offs:** Depends on the CKAN metadata schema, which could also change (but would fail loudly).

---

## 011 · Raw layer: original files on disk, Hive-style partitions

**Decision:** Store source files untouched under `data/raw/`, partitioned as `key=value` folders. From yearly ZIPs, only the monthly CSV files are extracted.

**Reasoning:**
- Raw data is the source of truth: any transformation can be rebuilt without downloading again.
- Extracting a CSV from a ZIP does not change its bytes; the ZIP is just packaging. TXT and XML copies add nothing.
- Only the file name of each ZIP member is kept, which also prevents "zip slip" path traversal.
- DuckDB reads Hive-style partitions natively.

**Trade-offs:** Local disk instead of object storage (S3/GCS), which would be the production equivalent.

---

## 012 · Idempotent, incremental extraction

**Decision:** Every extraction can be re-run safely. Files are written atomically (temporary file + rename). Unchanged data is not downloaded again.

**Reasoning:**
- Closed years are downloaded once. The open air quality period is downloaded again only when the CKAN file hash changes (stored in a `_fingerprint.txt` marker, written last).
- A past weather year is skipped only if its file reaches December 31 at 23:00, so the last days of a year are never lost.
- Verified in practice: after a run failed with HTTP 429 errors, re-running resumed exactly where it stopped.

**Trade-offs:** More logic than a naive "download everything every time".

---

## 013 · Weather: Open-Meteo archive, up to yesterday

**Decision:** One request per station and year, in UTC (`timezone=GMT`), with seven variables: temperature, relative humidity, precipitation, wind speed, wind direction, shortwave radiation and boundary layer height. Data is requested only up to yesterday (Madrid time).

**Reasoning:**
- Variables chosen for their known effect on pollution (dispersion, washout, ozone formation, thermal inversions).
- Exploration showed the archive endpoint returns values even for hours that have not happened yet, which can only be forecasts. Limiting to yesterday ensures no unobserved hours are stored.
- The current year is downloaded again on every run, so provisional recent values get revised automatically.
- Parallel arrays are validated to have equal length, because `zip()` silently truncates.

**Trade-offs:** Recent days are model data that may still be revised. Today's air quality has no weather match until tomorrow.

---

## 014 · HTTP retries only for transient errors

**Decision:** Retry network errors, HTTP 429 and 5xx. Fail immediately on other 4xx errors. On 429, honour the `Retry-After` header or wait 60 seconds.

**Reasoning:**
- Errors like 404 are not fixed by retrying; failing fast reports them sooner.
- The first weather run hit the API rate limit; short exponential backoff was not enough.
- Every request has a timeout, so a silent server can never hang the pipeline.

**Trade-offs:** Long waits on rate limits slow down the first full extraction.

---

## 018 · Air quality staging: unpivot, DST handling and source precedence

**Decision:** Unpivot the 24 hourly value/flag pairs into one row per station, pollutant and hour. Convert local time to UTC from the period start. Drop local hours that do not exist. When sources overlap, keep the valid row first, then historical over real-time.

**Reasoning:**
- Non-existent local times (the hour skipped in March) are detected with a round trip (local → UTC → local) instead of relying on how the time zone library resolves the gap.
- In October the repeated local hour appears only once in the source, so one UTC hour has no data. It is left as a gap, never imputed (decision 009).
- Placeholder rows (`0` flagged `N`) must never hide a valid value from the other source, so validity ranks above source precedence.

**Trade-offs:** The repeated October hour is assigned to one of its two possible UTC instants by the time zone library.

---

## 019 · dbt_utils package

**Decision:** Use `dbt-labs/dbt_utils` for multi-column uniqueness tests.

**Reasoning:** It is the de facto standard dbt package, maintained by dbt Labs. Writing the same test by hand would add code without adding value.

**Trade-offs:** One external dependency, pinned in `package-lock.yml`.

---

---

## 020 · Fact table grain: station × pollutant × hour (long format)

**Decision:** `fct_air_quality_weather` has one row per station, pollutant and hour, with the weather of that station and hour as columns.

**Alternatives considered:** One row per station and hour with one column per pollutant (wide format).

**Reasoning:**
- New pollutants need no schema change; each row carries its own unit.
- Filtering by pollutant is natural for dashboards. Wide views for correlation analysis can be derived with `PIVOT`.

**Trade-offs:** Weather values are repeated for every pollutant measured at the same station and hour.

---

## 021 · Weather joined with a left join

**Decision:** Air quality is the driving table; weather is attached with a left join on station and UTC hour.

**Reasoning:** Recent hours have air quality data but no weather yet (decision 013). They are kept with NULL weather instead of being dropped.

**Trade-offs:** Consumers must handle NULL weather columns for the most recent hours.

---

## 022 · Pollutant catalogue as a dbt seed

**Decision:** Pollutant codes, symbols, names and units live in `seeds/pollutants.csv`, built from the official file documentation.

**Reasoning:** Small, static reference data with no API. Versioned with the code and tested: every code in the data must exist in the catalogue.

**Trade-offs:** Must be updated by hand if the city council adds new pollutants (the relationship test will fail when that happens).

## 023 · Python tests: pytest with monkeypatch, no network

**Decision:** Test the extraction code with pytest. HTTP is replaced with pytest's `monkeypatch`; tests never reach the network or the real `data/` directory.

**Alternatives considered:** The `responses` and `requests-mock` libraries.

**Reasoning:**
- `requests.get` is called from a single function (`fetch`); everything else calls `fetch`. Replacing those two entry points is enough.
- Fakes return real `requests.Response` objects, so `raise_for_status()` behaves exactly as in production.
- `time.sleep` is replaced with a recorder: retry tests run instantly and assert the exact waits.
- No extra dependency.

**Trade-offs:** Mocking happens above the transport layer, so low-level networking details (sessions, adapters) are not exercised.

---

## 024 · Base model for air quality, to unit test time zone logic

**Decision:** Split the air quality model: `base_air_quality` reshapes the raw files (union, unpivot, typing); `stg_air_quality` applies UTC conversion, DST handling and source precedence. dbt unit tests cover the second one.

**Reasoning:**
- dbt unit tests need input relations with known columns. Mocking a `read_csv()` source with 57 wide columns would be fragile and unreadable.
- The riskiest logic (DST edge cases, precedence) is now tested with a few explicit rows, independent of real data.
- The autumn DST test pins the time zone library behaviour verified on real data, acting as a regression test.

**Trade-offs:** One more model in the DAG.

---

## 025 · Recent air quality from the accumulated real-time dataset

**Decision:** Download the real-time dataset that accumulates the last 30 days instead of the current-day file. Each download is stored untouched under `realtime/date=<download date>/`. When downloads overlap, the most recent one wins (after validity and historical precedence).

**Alternatives considered:** Keep the current-day file and run the extraction every hour.

**Reasoning:**
- The historical file is updated monthly; the current-day file only covers today. Any day without a late download was lost for good (verified: 30 of 31 October days were missing).
- With 30 days per download, a daily run heals any gap shorter than a month, including missed runs.
- The file comes from a paginated API: the extraction requests a 50,000-row page and fails if the response fills the page (possible truncation) or contains fewer than 20 stations (23 observed).

**Trade-offs:** Overlapping downloads take more disk space (~0.5 MB each) and need an extra tie-break rule.

---

## 026 · Airflow deployment: reduced Docker Compose with LocalExecutor

**Decision:** Run Airflow 3 with a custom Docker Compose file: Postgres, scheduler, DAG processor, API server and an init job, using LocalExecutor and a custom image.

**Alternatives considered:** The official Docker Compose file (CeleryExecutor, Redis, worker, triggerer).

**Reasoning:**
- Celery distributes tasks across machines; on a single machine it only adds Redis and a worker.
- About half the memory of the official setup, which matters on a 7.6 GB WSL machine.
- The triggerer only serves deferrable tasks, which this project does not use.

**Trade-offs:** Departs from the official file, so upgrades must be checked by hand.

---

## 027 · dbt in Airflow: Cosmos, isolated virtual environment, one model at a time

**Decision:** Render the dbt project with Astronomer Cosmos (one Airflow task per model and test). dbt lives in its own virtual environment inside the image. dbt tasks run one at a time.

**Alternatives considered:** A single `BashOperator` running `dbt build`.

**Reasoning:**
- Per-model tasks show the dbt graph in Airflow and allow retrying only the failed model.
- dbt and Airflow have large, conflicting dependency trees; a separate virtual environment avoids conflicts. dbt moved to a `transform` dependency group, so installing the pipeline package in Airflow does not pull dbt in.
- DuckDB allows a single writer process. Running dbt tasks one at a time avoids lock errors.
- Cosmos is configured with `InvocationMode.SUBPROCESS` for both parsing (`dbt ls`) and execution. In Cosmos 1.16, `RenderConfig.invocation_mode` defaults to `DBT_RUNNER`, which imports dbt as a library inside Airflow's environment.
- The dbt project lives in `/opt/pipeline/dbt`, outside `/opt/airflow`: a folder named `dbt` in the working directory is importable as a namespace package and can shadow the real dbt.
- dbt unit tests are excluded from the DAG: they test code, not data, and run in CI.

**Trade-offs:** Sequential dbt tasks are slower than a parallel warehouse would allow; this is a DuckDB limit (decision 001), not an Airflow one.

---

## 028 · One daily DAG

**Decision:** A single DAG runs daily at 06:00 Madrid time: the four extractions (weather after stations, the rest in parallel), then the dbt project through Cosmos.

**Alternatives considered:** Separate hourly and daily DAGs connected through Airflow Assets; a `dbt source freshness` step.

**Reasoning:**
- Weather is only available up to yesterday (decision 013), so hourly runs would not improve the analysis.
- With the 30-day accumulated file (decision 025), a missed day is recovered on the next run.
- Source freshness detects stale data delivered by external loaders. Here the extraction is part of the same DAG: a failed download fails its task, and a successful one always writes the current date's partition, so a freshness check would add a step without detecting anything new.

**Trade-offs:** Air quality in the warehouse is up to one day old.

---

## 029 · Continuous integration with GitHub Actions

**Decision:** Every push to `main` and every pull request runs four parallel jobs: lint (ruff), Python tests (pytest), dbt build on fixture data (models, data tests and unit tests), and a Docker image build that imports the DAG inside the image.

**Reasoning:**
- Each job maps to a class of failure seen during development: style and import errors, extraction logic, SQL and time zone logic, and image or DAG configuration (the Cosmos parsing issue in phase 5).
- dbt unit tests run here rather than in the daily DAG: they test code, so they belong to code changes.
- `uv sync --locked` fails if `uv.lock` is out of date, so CI tests the exact locked versions.
- Least privilege: the workflow can only read the repository. Third-party actions are pinned to full versions.

**Trade-offs:** The Docker job takes several minutes. The DAG import check runs without Airflow's metadata database, so it validates parsing, not scheduling.

---

## 030 · Ruff as linter and formatter

**Decision:** Use ruff for linting (rules E, W, F, I, UP, B) and formatting, with a 100-character line length.

**Alternatives considered:** flake8 + isort + black.

**Reasoning:** One tool replaces three, runs in milliseconds and is the current standard for new Python projects. Line length is left to the formatter (E501 ignored), since long strings and URLs are not split.

**Trade-offs:** None significant for a project of this size.

---

## 031 · Fixture dataset for dbt in CI

**Decision:** Commit a small dataset (`tests/fixtures/data`, ~90 KB) that reproduces the real raw formats, and run the full dbt build on it in CI.

**Reasoning:**
- The real raw data is not in the repository (decision 011), but dbt needs files to read.
- The fixtures reproduce every quirk found so far: BOM and CRLF, decimal commas, quoted values, both DST days (including the `0 N` placeholder for the non-existent hour), overlapping real-time downloads and Hive-style partitions.

**Trade-offs:** Fixtures must be updated by hand if the source formats change.
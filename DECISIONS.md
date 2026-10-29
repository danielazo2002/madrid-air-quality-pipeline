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
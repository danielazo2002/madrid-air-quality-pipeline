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
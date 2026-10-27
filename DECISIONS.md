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

**Alternatives considered:** EMT / BiciMAD (requires registration) and the GitHub API (more generic, less original).

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
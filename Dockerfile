# Custom Airflow image for the Madrid air quality pipeline (decisions 026 and 027).
ARG AIRFLOW_VERSION=3.3.2
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

# Re-declared: an ARG defined before FROM is not visible after it.
ARG AIRFLOW_VERSION=3.3.2

# 1. dbt in its own virtual environment, isolated from Airflow's dependencies.
#    Versions match uv.lock, so Airflow runs the same dbt as local development.
RUN python -m venv /opt/airflow/dbt_venv \
    && /opt/airflow/dbt_venv/bin/pip install --no-cache-dir \
        "dbt-core==1.12.6" \
        "dbt-duckdb==1.11.1"

# 2. Airflow's environment: Cosmos and the extraction package.
#    Pinning apache-airflow in the same command stops pip from upgrading it by accident.
COPY --chown=airflow:root pyproject.toml README.md /opt/pipeline/
COPY --chown=airflow:root src /opt/pipeline/src
RUN pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        "astronomer-cosmos>=1.14,<2" \
        /opt/pipeline

# 3. The dbt project, with its packages installed at build time.
#    Outside /opt/airflow: that folder is on Python's import path, and a directory
#    named "dbt" there is importable as a namespace package, shadowing the real dbt.
#    Group-writable because containers run with an arbitrary user id in group 0.
COPY --chown=airflow:root dbt /opt/pipeline/dbt
RUN cd /opt/pipeline/dbt \
    && DBT_SEND_ANONYMOUS_USAGE_STATS=false /opt/airflow/dbt_venv/bin/dbt deps \
    && chmod -R g+w /opt/pipeline/dbt
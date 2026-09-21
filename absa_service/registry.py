"""Model registry: MLflow tracking + a `model_runs` row per trained model version.

MLflow uses a local file store (./mlruns) by default; set MLFLOW_TRACKING_URI to point
at a server. Failure to reach MLflow never blocks training - the run is still recorded
in Postgres/SQLite.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from storage.models import ModelRun

log = logging.getLogger(__name__)
EXPERIMENT = "sentari-absa-ladder"


def log_to_mlflow(name: str, params: dict, metrics: dict, artifacts_dir: str | None = None,
                  tags: dict | None = None) -> str:
    try:
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "file:./mlruns"))
        mlflow.set_experiment(EXPERIMENT)
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
            if tags:
                mlflow.set_tags(tags)
            if artifacts_dir and os.path.isdir(artifacts_dir):
                mlflow.log_artifacts(artifacts_dir, artifact_path=name)
            return run.info.run_id
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow logging failed for %s: %s", name, exc)
        return ""


def register_run(session: Session, name: str, metrics: dict, mlflow_run_id: str = "",
                 version: str | None = None) -> ModelRun:
    version = version or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    run = ModelRun(name=name, version=version, mlflow_run_id=mlflow_run_id, metrics=metrics)
    session.add(run)
    session.flush()
    return run


def set_serving(session: Session, name: str) -> ModelRun | None:
    """Mark the latest run of `name` as the one serving traffic (and unmark others)."""
    latest = session.scalars(select(ModelRun).where(ModelRun.name == name)
                             .order_by(ModelRun.id.desc())).first()
    if latest is None:
        return None
    session.execute(update(ModelRun).values(serving=False))
    latest.serving = True
    session.flush()
    return latest


def serving_model(session: Session) -> ModelRun | None:
    return session.scalars(select(ModelRun).where(ModelRun.serving.is_(True))
                           .order_by(ModelRun.id.desc())).first()

# MLflow

Experiment `sentari-absa-ladder` holds one run per model on the ladder (params, gold-set metrics,
latency, training time). By default runs are written to `./mlruns` (file store). To use the server in
`docker-compose.yml`:

    export MLFLOW_TRACKING_URI=http://localhost:5000
    python -m absa_service.train --transformer

The `model_runs` table mirrors every run (name, version, MLflow run id, metrics) and carries the
`serving` flag that decides which model the API loads (`GET /models`).

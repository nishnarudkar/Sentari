"""Model loading for serving: picks the model marked `serving` in the registry (or SENTARI_MODEL)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from absa_service.models.base import SentimentModel

ARTIFACTS_MODELS = Path(os.environ.get("SENTARI_ARTIFACTS", "artifacts")) / "models"
DEFAULT_MODEL = "lm_directional"


def build_model(name: str) -> SentimentModel:
    from absa_service.models import classical_ml, deep_learning, lexicon
    factories = {
        "vader": lexicon.VaderModel, "sentiwordnet": lexicon.SentiWordNetModel,
        "lm_lexicon": lexicon.LoughranMcDonaldModel, "lm_directional": lexicon.LMDirectionalModel,
        "nb_tfidf": classical_ml.NaiveBayesModel, "dt_tfidf": classical_ml.DecisionTreeModel,
        "cnn": deep_learning.CnnModel, "lstm": deep_learning.LstmModel,
    }
    if name in ("finbert_ft", "finbert_zeroshot"):
        from absa_service.models.transformer import TransformerModel
        model = TransformerModel(name=name, zero_shot=(name == "finbert_zeroshot"))
        return model.load(ARTIFACTS_MODELS) if name == "finbert_ft" and (ARTIFACTS_MODELS / name).exists() \
            else model.fit([], None)
    if name not in factories:
        raise ValueError(f"unknown model '{name}'")
    model = factories[name]()
    if model.trainable:
        model.load(ARTIFACTS_MODELS)  # raises FileNotFoundError if not trained yet
    return model


def registry_serving_name() -> str | None:
    """Name of the model flagged `serving` in the model registry (None if the DB/registry is empty)."""
    try:
        from absa_service.registry import serving_model
        from storage.db import get_engine, make_session_factory
        with make_session_factory(get_engine())() as session:
            run = serving_model(session)
            return run.name if run else None
    except Exception:  # noqa: BLE001 - no DB yet / tables missing
        return None


@lru_cache(maxsize=4)
def get_model(name: str | None = None) -> SentimentModel:
    """Resolution order: explicit name > SENTARI_MODEL env > registry `serving` flag > rule-based default."""
    name = name or os.environ.get("SENTARI_MODEL") or registry_serving_name() or DEFAULT_MODEL
    try:
        return build_model(name)
    except FileNotFoundError:
        return build_model(DEFAULT_MODEL)  # trained weights missing -> fall back to the rule-based model

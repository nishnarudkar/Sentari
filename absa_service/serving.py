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


@lru_cache(maxsize=4)
def get_model(name: str | None = None) -> SentimentModel:
    name = name or os.environ.get("SENTARI_MODEL", DEFAULT_MODEL)
    try:
        return build_model(name)
    except FileNotFoundError:
        return build_model(DEFAULT_MODEL)  # trained weights missing -> fall back to the rule-based model

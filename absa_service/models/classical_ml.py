"""Classical ML rung: TF-IDF + Multinomial Naive Bayes / Decision Tree.

Features: word 1-2 grams over negation-marked tokens with an aspect token prepended,
so the model can learn aspect-conditional polarity ("asp_margins" x "fell").
"""
from __future__ import annotations

import pickle
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from absa_service.models.base import SentimentModel, marked_tokens, prediction_from_probs
from absa_service.schemas import LABELS, Item, Prediction


def _featurize(item: Item) -> str:
    return " ".join(marked_tokens(item.text, item.aspect))


class _SklearnModel(SentimentModel):
    trainable = True

    def __init__(self, classifier, name: str):
        self.name = name
        self.pipe = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, token_pattern=r"[^\s]+")),
            ("clf", classifier),
        ])

    def fit(self, train, val=None):
        X = [_featurize(e.item()) for e in train]
        y = [e.label for e in train]
        self.pipe.fit(X, y)
        return self

    def predict(self, items: list[Item]) -> list[Prediction]:
        proba = self.pipe.predict_proba([_featurize(i) for i in items])
        classes = list(self.pipe.classes_)
        out = []
        for row in proba:
            probs = {l: 0.0 for l in LABELS}
            probs.update({c: float(p) for c, p in zip(classes, row)})
            out.append(prediction_from_probs(probs))
        return out

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / f"{self.name}.pkl").open("wb") as fh:
            pickle.dump(self.pipe, fh)

    def load(self, directory: Path):
        with (directory / f"{self.name}.pkl").open("rb") as fh:
            self.pipe = pickle.load(fh)
        return self


class NaiveBayesModel(_SklearnModel):
    def __init__(self, alpha: float = 0.3):
        super().__init__(MultinomialNB(alpha=alpha), "nb_tfidf")


class DecisionTreeModel(_SklearnModel):
    def __init__(self, max_depth: int = 24, seed: int = 0):
        super().__init__(DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=2, random_state=seed),
                         "dt_tfidf")

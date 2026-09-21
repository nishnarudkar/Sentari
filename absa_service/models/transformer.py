"""Transformer rung: fine-tuned FinBERT-class encoder (PyTorch + Hugging Face transformers).

The aspect is fed as the second segment of a sentence pair ("<clause>" [SEP] "aspect: margins"),
the standard aspect-based-sentiment formulation (sentence-pair / auxiliary-sentence, Sun et al. 2019),
so one encoder serves all six aspects.

Base checkpoint defaults to ProsusAI/finbert (override with SENTARI_BASE_MODEL, e.g. a
local path or any BERT-family checkpoint). `zero_shot=True` uses the base model without
fine-tuning, which is a useful extra ladder rung (document-level FinBERT prior).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from absa_service.models.base import SentimentModel, prediction_from_probs
from absa_service.schemas import LABELS, Item, Prediction

DEFAULT_BASE = os.environ.get("SENTARI_BASE_MODEL", "ProsusAI/finbert")
LABEL_IDX = {l: i for i, l in enumerate(LABELS)}


def _aspect_prompt(aspect: str) -> str:
    return f"aspect: {aspect.replace('_', ' ')}"


class TransformerModel(SentimentModel):
    trainable = True

    def __init__(self, base: str = DEFAULT_BASE, name: str = "finbert_ft", epochs: int = 2, lr: float = 3e-5,
                 batch_size: int = 16, max_len: int = 96, seed: int = 0, zero_shot: bool = False,
                 max_train: int | None = None):
        self.base, self.name = base, name
        self.epochs, self.lr, self.batch_size, self.max_len, self.seed = epochs, lr, batch_size, max_len, seed
        self.zero_shot, self.max_train = zero_shot, max_train
        self.tok = None
        self.net = None
        self._label_map: list[int] | None = None  # model output index for each of LABELS
        self.history: list[dict] = []
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def _init_net(self, num_labels_fresh: bool):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(self.base)
        self.net = AutoModelForSequenceClassification.from_pretrained(
            self.base, num_labels=3, ignore_mismatched_sizes=True,
            id2label=dict(enumerate(LABELS)), label2id=LABEL_IDX) if num_labels_fresh else \
            AutoModelForSequenceClassification.from_pretrained(self.base)
        self.net.to(self.device)

    def _resolve_label_map(self):
        """Map our LABELS order onto the checkpoint's id2label (FinBERT is positive/negative/neutral)."""
        id2label = {int(k): v.lower() for k, v in self.net.config.id2label.items()}
        rev = {v: k for k, v in id2label.items()}
        self._label_map = [rev[l] for l in LABELS] if all(l in rev for l in LABELS) else [0, 1, 2]

    def _batch(self, items: list[Item]):
        enc = self.tok([i.text for i in items], [_aspect_prompt(i.aspect) for i in items],
                       truncation=True, max_length=self.max_len, padding=True, return_tensors="pt")
        return {k: v.to(self.device) for k, v in enc.items()}

    def fit(self, train, val=None):
        torch.manual_seed(self.seed); np.random.seed(self.seed)
        if self.zero_shot:
            self._init_net(num_labels_fresh=False)
            self._resolve_label_map()
            return self
        # start from the checkpoint's own head when it already has our 3 labels (FinBERT does)
        self._init_net(num_labels_fresh=False)
        self._resolve_label_map()
        if self.max_train:
            train = train[: self.max_train]
        opt = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=0.01)
        n = len(train)
        steps = self.epochs * ((n + self.batch_size - 1) // self.batch_size)
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / max(1, steps)))
        for epoch in range(self.epochs):
            self.net.train()
            order = np.random.permutation(n)
            total = 0.0
            for i in range(0, n, self.batch_size):
                batch = [train[j] for j in order[i:i + self.batch_size]]
                enc = self._batch([e.item() for e in batch])
                y = torch.tensor([self._label_map[LABEL_IDX[e.label]] for e in batch], device=self.device)
                loss = F.cross_entropy(self.net(**enc).logits, y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
                total += loss.item() * len(batch)
            rec = {"epoch": epoch + 1, "train_loss": total / n}
            if val:
                preds = self.predict([e.item() for e in val])
                rec["val_acc"] = float(np.mean([p.label == e.label for p, e in zip(preds, val)]))
            self.history.append(rec)
        return self

    @torch.no_grad()
    def predict(self, items: list[Item]) -> list[Prediction]:
        assert self.net is not None, "model not loaded"
        self.net.eval()
        out: list[Prediction] = []
        for i in range(0, len(items), 32):
            enc = self._batch(items[i:i + 32])
            probs = F.softmax(self.net(**enc).logits, dim=-1).cpu().numpy()
            for p in probs:
                out.append(prediction_from_probs({l: float(p[self._label_map[k]]) for k, l in enumerate(LABELS)}))
        return out

    def save(self, directory: Path) -> None:
        target = directory / self.name
        target.mkdir(parents=True, exist_ok=True)
        self.net.save_pretrained(target)
        self.tok.save_pretrained(target)

    def load(self, directory: Path):
        self.base = str(directory / self.name)
        self._init_net(num_labels_fresh=False)
        self._resolve_label_map()
        return self

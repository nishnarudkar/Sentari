"""Deep-learning rung: CNN (Kim-style) and BiLSTM classifiers in PyTorch.

Embeddings are learned from scratch by default. To use pre-trained vectors set
SENTARI_GLOVE to a GloVe-format text file (e.g. glove.6B.100d.txt); matching words
are initialised from it (project.md: "LSTM with pre-trained embeddings").
"""
from __future__ import annotations

import json
import os
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from absa_service.models.base import SentimentModel, marked_tokens, prediction_from_probs
from absa_service.schemas import LABELS, Item, Prediction

PAD, UNK = 0, 1
MAX_LEN = 48
LABEL_IDX = {l: i for i, l in enumerate(LABELS)}


def _tokens(item: Item) -> list[str]:
    return marked_tokens(item.text, item.aspect)[:MAX_LEN]


def _load_glove(path: str, vocab: dict[str, int], dim: int) -> np.ndarray | None:
    p = Path(path)
    if not p.exists():
        return None
    mat = np.random.normal(0, 0.1, (len(vocab), dim)).astype("float32")
    mat[PAD] = 0
    found = 0
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip().split(" ")
            word = parts[0]
            if len(parts) != dim + 1:
                continue
            vec = np.asarray(parts[1:], dtype="float32")
            if word in vocab:
                mat[vocab[word]] = vec
                found += 1
            if f"NEG_{word}" in vocab:  # negated tokens start from a damped, sign-flipped vector
                mat[vocab[f"NEG_{word}"]] = -vec * 0.5
    return mat if found else None


class TextCNN(nn.Module):
    def __init__(self, vocab_size, emb_dim=100, n_filters=64, kernel_sizes=(2, 3, 4), n_classes=3, dropout=0.4):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=PAD)
        self.convs = nn.ModuleList(nn.Conv1d(emb_dim, n_filters, k, padding=k // 2) for k in kernel_sizes)
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(n_filters * len(kernel_sizes), n_classes)

    def forward(self, x):
        e = self.emb(x).transpose(1, 2)
        pooled = [F.relu(c(e)).max(dim=2).values for c in self.convs]
        return self.fc(self.drop(torch.cat(pooled, dim=1)))


class BiLSTM(nn.Module):
    def __init__(self, vocab_size, emb_dim=100, hidden=96, n_classes=3, dropout=0.4):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=PAD)
        self.lstm = nn.LSTM(emb_dim, hidden, batch_first=True, bidirectional=True)
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden * 2, n_classes)

    def forward(self, x):
        mask = (x != PAD).unsqueeze(-1)
        out, _ = self.lstm(self.emb(x))
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1)  # masked mean pooling
        return self.fc(self.drop(pooled))


class _TorchModel(SentimentModel):
    trainable = True
    arch = "cnn"

    def __init__(self, epochs: int = 12, lr: float = 2e-3, batch_size: int = 64, seed: int = 0, emb_dim: int = 100):
        self.epochs, self.lr, self.batch_size, self.seed, self.emb_dim = epochs, lr, batch_size, seed, emb_dim
        self.vocab: dict[str, int] = {"<pad>": PAD, "<unk>": UNK}
        self.net: nn.Module | None = None
        self.history: list[dict] = []

    # -- helpers
    def _build(self, vocab_size: int, emb: np.ndarray | None) -> nn.Module:
        raise NotImplementedError

    def _encode(self, items: list[Item]) -> torch.Tensor:
        rows = []
        for it in items:
            ids = [self.vocab.get(t, UNK) for t in _tokens(it)]
            rows.append(ids + [PAD] * (MAX_LEN - len(ids)))
        return torch.tensor(rows, dtype=torch.long)

    def fit(self, train, val=None):
        random.seed(self.seed); np.random.seed(self.seed); torch.manual_seed(self.seed)
        counts = Counter(t for e in train for t in _tokens(e.item()))
        for tok, c in counts.items():
            if c >= 1:
                self.vocab.setdefault(tok, len(self.vocab))
        glove = os.environ.get("SENTARI_GLOVE")
        emb = _load_glove(glove, self.vocab, self.emb_dim) if glove else None
        self.net = self._build(len(self.vocab), emb)
        X = self._encode([e.item() for e in train])
        y = torch.tensor([LABEL_IDX[e.label] for e in train])
        opt = torch.optim.Adam(self.net.parameters(), lr=self.lr, weight_decay=1e-5)
        best_state, best_val = None, -1.0
        for epoch in range(self.epochs):
            self.net.train()
            perm = torch.randperm(len(X))
            total = 0.0
            for i in range(0, len(X), self.batch_size):
                idx = perm[i:i + self.batch_size]
                opt.zero_grad()
                loss = F.cross_entropy(self.net(X[idx]), y[idx])
                loss.backward()
                opt.step()
                total += loss.item() * len(idx)
            rec = {"epoch": epoch + 1, "train_loss": total / len(X)}
            if val:
                preds = self.predict([e.item() for e in val])
                rec["val_acc"] = float(np.mean([p.label == e.label for p, e in zip(preds, val)]))
                if rec["val_acc"] > best_val:
                    best_val = rec["val_acc"]
                    best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
            self.history.append(rec)
        if best_state is not None:
            self.net.load_state_dict(best_state)
        return self

    @torch.no_grad()
    def predict(self, items: list[Item]) -> list[Prediction]:
        assert self.net is not None, "model not trained"
        self.net.eval()
        probs = F.softmax(self.net(self._encode(items)), dim=-1).numpy()
        return [prediction_from_probs({l: float(p[LABEL_IDX[l]]) for l in LABELS}) for p in probs]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        torch.save(self.net.state_dict(), directory / f"{self.name}.pt")
        (directory / f"{self.name}.vocab.json").write_text(json.dumps(self.vocab), encoding="utf-8")

    def load(self, directory: Path):
        self.vocab = json.loads((directory / f"{self.name}.vocab.json").read_text(encoding="utf-8"))
        self.net = self._build(len(self.vocab), None)
        self.net.load_state_dict(torch.load(directory / f"{self.name}.pt", map_location="cpu"))
        return self


def _init_emb(net: nn.Module, emb: np.ndarray | None) -> nn.Module:
    if emb is not None:
        net.emb.weight.data.copy_(torch.from_numpy(emb))
    return net


class CnnModel(_TorchModel):
    name = "cnn"

    def _build(self, vocab_size, emb):
        return _init_emb(TextCNN(vocab_size, self.emb_dim), emb)


class LstmModel(_TorchModel):
    name = "lstm"

    def _build(self, vocab_size, emb):
        return _init_emb(BiLSTM(vocab_size, self.emb_dim), emb)

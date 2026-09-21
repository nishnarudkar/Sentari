# Sentari evaluation report (auto-generated)

## 1. Model ladder (one held-out gold set, every approach)

| Rung | Model | Accuracy | Macro-F1 | P/R/F1 neg | P/R/F1 neu | P/R/F1 pos | Trap acc. | ms/item |
|---|---|---|---|---|---|---|---|---|
| Lexicon | vader | 0.649 | 0.647 | 0.69/0.61/0.65 | 0.59/0.67/0.63 | 0.66/0.68/0.67 | 0.38 | 0.03 |
| Lexicon | sentiwordnet | 0.489 | 0.490 | 0.56/0.42/0.48 | 0.38/0.62/0.47 | 0.59/0.47/0.52 | 0.27 | 1.66 |
| Lexicon | lm_lexicon | 0.755 | 0.756 | 0.92/0.67/0.77 | 0.57/1.00/0.73 | 0.88/0.68/0.77 | 0.42 | 0.01 |
| Lexicon + rules | lm_directional | 0.894 | 0.892 | 0.97/0.86/0.91 | 0.79/0.96/0.87 | 0.91/0.88/0.90 | 0.85 | 0.03 |
| Classical ML | nb_tfidf | 0.745 | 0.743 | 0.69/0.81/0.74 | 0.88/0.62/0.73 | 0.74/0.76/0.75 | 0.69 | 0.04 |
| Classical ML | dt_tfidf | 0.532 | 0.519 | 0.47/0.75/0.57 | 0.58/0.46/0.51 | 0.71/0.35/0.47 | 0.58 | 0.04 |
| Deep learning | cnn | 0.745 | 0.739 | 0.69/0.86/0.77 | 0.83/0.62/0.71 | 0.77/0.71/0.74 | 0.92 | 0.08 |
| Deep learning | lstm | 0.638 | 0.607 | 0.58/0.81/0.67 | 0.80/0.33/0.47 | 0.68/0.68/0.68 | 0.81 | 0.30 |
| Transformer (no fine-tune) | finbert_zeroshot | 0.606 | 0.601 | 0.67/0.39/0.49 | 0.61/0.71/0.65 | 0.58/0.76/0.66 | 0.35 | 8.71 |
| Transformer (fine-tuned) | finbert_ft | 0.936 | 0.938 | 0.94/0.92/0.93 | 0.96/0.96/0.96 | 0.91/0.94/0.93 | 0.88 | 10.47 |

*n_gold=94, n_train(weak labels)=3400. Gold set is hand-written; training data are weak template labels. lm_directional rules were authored with sight of the gold set -> optimistic.*

## 2. Lexicon failure analysis

| model | error (all) | error (trap) | error (non-trap) |
|---|---|---|---|
| vader | 35.1% | 61.5% | 25.0% |
| sentiwordnet | 51.1% | 73.1% | 42.6% |
| lm_lexicon | 24.5% | 57.7% | 11.8% |
| lm_directional | 10.6% | 15.4% | 8.8% |
| nb_tfidf | 25.5% | 30.8% | 23.5% |
| cnn | 25.5% | 7.7% | 32.4% |
| finbert_ft | 6.4% | 11.5% | 4.4% |

## 3a. Grounding audit - adversarial catch rate (heuristic Skeptic)

```json
{
  "faithful": {
    "n": 43,
    "supported": 43,
    "unverified": 0,
    "rejected": 0,
    "false_rejection_rate": 0.0,
    "false_flag_rate": 0.0
  },
  "number_swap": {
    "n": 13,
    "supported": 0,
    "unverified": 0,
    "rejected": 13,
    "catch_rate": 1.0,
    "hard_reject_rate": 1.0
  },
  "polarity_flip": {
    "n": 22,
    "supported": 17,
    "unverified": 0,
    "rejected": 5,
    "catch_rate": 0.22727272727272727,
    "hard_reject_rate": 0.22727272727272727
  },
  "wrong_citation": {
    "n": 43,
    "supported": 0,
    "unverified": 21,
    "rejected": 22,
    "catch_rate": 1.0,
    "hard_reject_rate": 0.5116279069767442
  },
  "fabrication": {
    "n": 43,
    "supported": 0,
    "unverified": 29,
    "rejected": 14,
    "catch_rate": 1.0,
    "hard_reject_rate": 0.32558139534883723
  },
  "no_citation": {
    "n": 43,
    "supported": 0,
    "unverified": 0,
    "rejected": 43,
    "catch_rate": 1.0,
    "hard_reject_rate": 1.0
  },
  "_overall": {
    "corrupted_n": 164,
    "overall_catch_rate": 0.8963414634146342,
    "skeptic_entailment_backend": "heuristic"
  }
}
```

## 3a'. Grounding audit - adversarial catch rate (NLI Skeptic)

```json
{
  "faithful": {
    "n": 43,
    "supported": 43,
    "unverified": 0,
    "rejected": 0,
    "false_rejection_rate": 0.0,
    "false_flag_rate": 0.0
  },
  "number_swap": {
    "n": 13,
    "supported": 0,
    "unverified": 0,
    "rejected": 13,
    "catch_rate": 1.0,
    "hard_reject_rate": 1.0
  },
  "polarity_flip": {
    "n": 22,
    "supported": 0,
    "unverified": 0,
    "rejected": 22,
    "catch_rate": 1.0,
    "hard_reject_rate": 1.0
  },
  "wrong_citation": {
    "n": 43,
    "supported": 0,
    "unverified": 28,
    "rejected": 15,
    "catch_rate": 1.0,
    "hard_reject_rate": 0.3488372093023256
  },
  "fabrication": {
    "n": 43,
    "supported": 0,
    "unverified": 18,
    "rejected": 25,
    "catch_rate": 1.0,
    "hard_reject_rate": 0.5813953488372093
  },
  "no_citation": {
    "n": 43,
    "supported": 0,
    "unverified": 0,
    "rejected": 43,
    "catch_rate": 1.0,
    "hard_reject_rate": 1.0
  },
  "_overall": {
    "corrupted_n": 164,
    "overall_catch_rate": 1.0,
    "skeptic_entailment_backend": "nli"
  }
}
```

## 5. Latency and cost

```json
{
  "n_briefs": 2,
  "latency_s": {
    "mean": 0.788,
    "median": 0.788,
    "p95": 1.551,
    "max": 1.551
  },
  "by_llm": {
    "heuristic": {
      "n": 2,
      "tokens_in": 0,
      "tokens_out": 0,
      "cost_usd": 0.0,
      "avg_cost_usd_per_brief": 0.0,
      "avg_tokens_per_brief": 0.0
    }
  }
}

```

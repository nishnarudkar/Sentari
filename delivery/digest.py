"""Daily digest: the top-3 aspect-sentiment moves across the watchlist, via email (SMTP) and/or Slack.

Move = change in a ticker's per-document mean aspect score between its two most recent documents
that mention the aspect. Delivery is opt-in via env vars; without them the digest is only rendered.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import requests
from sqlalchemy.orm import Session

from absa_service.schemas import ASPECTS
from absa_service.signals import aspect_trajectory

DISCLAIMER = "Sentari is a research/decision-support tool. Not investment advice."


def top_moves(session: Session, tickers: list[str], n: int = 3, model_name: str | None = None) -> list[dict]:
    moves = []
    for t in tickers:
        for a in ASPECTS:
            traj = aspect_trajectory(session, t, a, model_name)
            if len(traj) >= 2:
                prev, last = traj[-2], traj[-1]
                moves.append({"ticker": t, "aspect": a, "from": prev["mean"], "to": last["mean"],
                              "change": round(last["mean"] - prev["mean"], 3), "date": last["date"],
                              "document_id": last["document_id"]})
    return sorted(moves, key=lambda m: abs(m["change"]), reverse=True)[:n]


def render_text(moves: list[dict], drift_alerts: list[dict] | None = None) -> str:
    lines = ["Sentari daily digest - top aspect-sentiment moves", ""]
    if not moves:
        lines.append("No aspect moves (need at least two documents per ticker/aspect).")
    for i, m in enumerate(moves, 1):
        arrow = "▲" if m["change"] > 0 else "▼"
        lines.append(f'{i}. {m["ticker"]} - {m["aspect"].replace("_", " ")}: {m["from"]:+.2f} -> {m["to"]:+.2f} '
                     f'({arrow} {m["change"]:+.2f}, as of {m["date"]})')
    for a in drift_alerts or []:
        lines.append(f'⚠ drift alert {a["ticker"]}: PSI={a["psi_aspect_mix"]}, confidence shift d={a["confidence_shift"]}')
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def send_email(text: str) -> bool:
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("DIGEST_TO")
    if not host or not to:
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Sentari daily digest", os.environ.get("SMTP_FROM", "sentari@localhost"), to
    msg.set_content(text)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        if os.environ.get("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    return True


def send_slack(text: str) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    return requests.post(url, json={"text": text}, timeout=15).ok


def deliver(session: Session, tickers: list[str], drift_alerts: list[dict] | None = None) -> dict:
    moves = top_moves(session, tickers)
    text = render_text(moves, drift_alerts)
    return {"text": text, "moves": moves, "email": send_email(text), "slack": send_slack(text)}

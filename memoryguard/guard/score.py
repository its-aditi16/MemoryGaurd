"""Explainable suspicion score: weighted sum of 0..1 signals, with each signal's share of the total."""
import json

import config
import db
from guard import detectors
from guard.provenance import now_iso
from store import Memory

LABELS = {
    "contradicts_verified": "Contradicts verified record",
    "low_trust": "Low-trust source",
    "injection_markers": "Injection markers",
    "attack_similarity": "Similar to known attack",
    "high_impact_field": "Touches high-impact field",
}


def status_for(score: float) -> str:
    if score >= config.QUARANTINE_THRESHOLD:
        return "quarantined"
    if score >= config.FLAG_THRESHOLD:
        return "flagged"
    return "live"


def score_memory(memory: Memory, use_cache: bool = True) -> dict:
    sha = memory.metadata.get("sha256", "")
    if use_cache:
        rows = db.query("SELECT sha256, result FROM scores WHERE memory_id = ?", (memory.id,))
        if rows and rows[0]["sha256"] == sha:
            return json.loads(rows[0]["result"])

    text, meta = memory.content, memory.metadata
    trust = float(meta.get("trust", 0))
    inj, markers = detectors.injection_markers(text)
    sim, phrase, cos = detectors.attack_similarity(text)
    impact, impact_fields = detectors.high_impact(text)
    contra, contra_detail = detectors.contradicts_verified(text, meta.get("source_class", ""), impact_fields)

    values = {
        "contradicts_verified": (contra, contra_detail or "No conflict with verified records"),
        "low_trust": (round(1 - trust, 3), f"{meta.get('source_class')} source, trust {trust:.1f}"),
        "injection_markers": (inj, ", ".join(markers) if markers else "None found"),
        "attack_similarity": (round(sim, 3), f"cosine {cos:.2f} to \"{phrase}\""),
        "high_impact_field": (impact, ", ".join(impact_fields) if impact_fields else "None"),
    }
    total = sum(config.WEIGHTS[k] * v for k, (v, _) in values.items())
    signals = []
    for key, (value, detail) in values.items():
        contribution = config.WEIGHTS[key] * value
        signals.append({
            "key": key, "label": LABELS[key], "value": round(value, 3), "weight": config.WEIGHTS[key],
            "contribution": round(contribution, 4),
            "share": round(contribution / total, 4) if total else 0.0,
            "detail": detail,
        })
    signals.sort(key=lambda s: -s["contribution"])
    result = {
        "memory_id": memory.id, "score": round(total, 4), "suggested_status": status_for(total),
        "thresholds": {"flag": config.FLAG_THRESHOLD, "quarantine": config.QUARANTINE_THRESHOLD},
        "signals": signals, "computed_at": now_iso(),
    }
    db.execute("INSERT OR REPLACE INTO scores (memory_id, sha256, result) VALUES (?, ?, ?)",
               (memory.id, sha, json.dumps(result)))
    return result


def explain(result: dict, top: int = 3) -> str:
    """'contradicts verified record 52%, low-trust source 26%, ...'"""
    parts = [f"{s['label'].lower()} {s['share'] * 100:.0f}%" for s in result["signals"][:top] if s["share"] > 0]
    return ", ".join(parts)

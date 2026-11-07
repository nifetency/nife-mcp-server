"""Pure helpers for the NERO (AI SRE) and FinOps tools (no MCP or network imports)."""
import re
from typing import Any, Dict, List, Optional

SEVERITIES = ("critical", "high", "medium", "low", "warning", "info")
INCIDENT_STATUSES = ("open", "investigating", "resolved", "closed")
ALERT_STATUSES = ("firing", "active", "acknowledged", "resolved")
# 'month', '7d', '30d', '2026-10' ...: the backend defines the vocabulary, so only the shape is checked.
PERIOD_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
# Sanity bounds for what the model may ask for.
MAX_TEXT = 4000


def clip(value: Any, limit: int = MAX_TEXT) -> Any:
    """Shorten long free text (AI analysis, descriptions) so one result cannot flood the context."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [truncated, {len(value) - limit} more characters]"
    return value


def check_choice(value: Optional[str], allowed: tuple, name: str) -> Optional[str]:
    """Lower-case a filter and check it against the known values; None passes through."""
    if value is None or value == "":
        return None
    low = str(value).strip().lower()
    if low not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return low


def check_period(period: Optional[str], default: str = "month") -> str:
    value = (period or default).strip()
    if not PERIOD_RE.match(value):
        raise ValueError("period must be a short token such as 'month', '7d' or '30d'.")
    return value


def pct(value: Any) -> Optional[float]:
    """0-1 confidences become percentages, rounded; anything non-numeric becomes None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(value * 100, 1) if 0 <= value <= 1 else round(float(value), 1)


def money(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


# --------------------------------------------------------------------- NERO
def incident_view(inc: Dict[str, Any], detail: bool = False) -> Dict[str, Any]:
    out = {
        "id": inc.get("id"), "app": inc.get("appName"), "service": inc.get("serviceName"),
        "type": inc.get("incidentType"), "severity": inc.get("severity"), "status": inc.get("status"),
        "title": inc.get("title"), "detected_at": inc.get("detectedAt"),
        "resolved_at": inc.get("resolvedAt"), "auto_resolved": inc.get("autoResolved"),
        "root_cause": clip(inc.get("rootCause"), 600),
        "root_cause_confidence_pct": pct(inc.get("rootCauseConfidence")),
        "root_cause_source": inc.get("rootCauseSource"),
    }
    if detail:
        out["description"] = clip(inc.get("description"))
        out["resolution"] = clip(inc.get("resolution"))
        out["indicators"] = [
            {k: i.get(k) for k in ("name", "value", "expected", "detail", "source", "severity")}
            for i in (inc.get("indicators") or [])[:15]
        ]
        pm = inc.get("postmortem")
        if pm:
            out["postmortem"] = {
                "duration_minutes": pm.get("durationMinutes"), "outcome": pm.get("outcome"),
                "root_cause": clip(pm.get("rootCause"), 800),
                "actions_taken": (pm.get("actionsTaken") or [])[:15],
                "timeline": (pm.get("timeline") or [])[:20],
                "lessons_learned": clip(pm.get("lessonsLearned"), 1200),
                "prevention": (pm.get("prevention") or [])[:10],
                "health_before": pm.get("healthBefore"), "health_after": pm.get("healthAfter"),
            }
    return out


def action_view(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "action": a.get("action"), "description": clip(a.get("description"), 600),
        "priority": a.get("priority"), "automated": a.get("automated"),
        "risk": a.get("riskLevel"), "confidence_pct": pct(a.get("confidence")),
    }


def alert_view(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": a.get("id"), "title": a.get("title"), "description": clip(a.get("description"), 600),
        "severity": a.get("severity"), "status": a.get("status"), "resource": a.get("resource"),
        "kind": a.get("kind"), "raised_at": a.get("timestamp"),
        "acknowledged_by": a.get("acknowledgedBy"), "acknowledged_at": a.get("acknowledgedAt"),
        "resolved_by": a.get("resolvedBy"), "resolved_at": a.get("resolvedAt"),
    }


def slo_attention(slo: Dict[str, Any]) -> List[str]:
    """Plain-language flags for an SLO record, so the model does not have to interpret raw numbers."""
    notes: List[str] = []
    if slo.get("breaching"):
        notes.append("The SLO is being breached: availability is below target.")
    left = slo.get("errorBudgetPct")
    if isinstance(left, (int, float)) and left < 25:
        notes.append(f"Only {round(left, 1)}% of the error budget is left.")
    burn = slo.get("burnRate1h")
    if isinstance(burn, (int, float)) and burn > 1:
        notes.append(f"The error budget is burning {round(burn, 1)}x faster than sustainable (last hour).")
    days = slo.get("daysRemaining")
    if isinstance(days, (int, float)) and 0 <= days < 3 and not slo.get("breaching"):
        notes.append(f"At the current burn rate the budget lasts about {round(days, 1)} more days.")
    if slo.get("targetIsDefault"):
        notes.append("No SLO target is saved for this app, so the 99.9% default is used.")
    return notes


# ------------------------------------------------------------------- FinOps
def unwrap_list(data: Any, *keys: str) -> List[Any]:
    """A bare list, or the first list found under one of the keys (the FinOps API uses both shapes)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
    return []


def extract_monthly_savings(rec: Dict[str, Any]) -> float:
    """Monthly savings of a recommendation. The service has returned several shapes, so every one
    the dashboard accepts is accepted here; a missing value is 0, never an invented number."""
    s = rec.get("estimatedSavings", rec.get("estimated_savings", rec.get("savings")))
    if isinstance(s, bool):
        s = None
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, dict):
        for key in ("monthly", "Monthly", "month", "amount"):
            v = s.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
    for key in ("monthlySavings", "monthly_savings", "potential_savings", "potentialSavings"):
        v = rec.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return 0.0


def normalize_recommendation(rec: Dict[str, Any]) -> Dict[str, Any]:
    conf = rec.get("confidence", rec.get("confidence_score"))
    return {
        "id": rec.get("id") or rec.get("_id"),
        "title": rec.get("title") or rec.get("name") or "Untitled recommendation",
        "description": clip(rec.get("description") or rec.get("details") or "", 800),
        "category": rec.get("category") or rec.get("type"),
        "priority": rec.get("priority") or rec.get("impact"),
        "effort": rec.get("effort") or rec.get("implementation_effort"),
        "risk": rec.get("risk"),
        "monthly_savings": round(extract_monthly_savings(rec), 2),
        "confidence_pct": pct(conf),
        "provider": rec.get("provider"), "region": rec.get("region"),
        "resource_id": rec.get("resourceId") or rec.get("resource_id"),
        "instances": (rec.get("instances") or [])[:10],
    }


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def rank_recommendations(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Biggest saving first within each priority band."""
    return sorted(
        recs,
        key=lambda r: (_PRIORITY_ORDER.get(str(r.get("priority") or "").lower(), 3), -r["monthly_savings"]),
    )


def summarize_recommendations(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(r["monthly_savings"] for r in recs)
    by_cat: Dict[str, Dict[str, Any]] = {}
    for r in recs:
        c = by_cat.setdefault(str(r.get("category") or "other"), {"count": 0, "monthly_savings": 0.0})
        c["count"] += 1
        c["monthly_savings"] = round(c["monthly_savings"] + r["monthly_savings"], 2)
    return {
        "count": len(recs),
        "total_monthly_savings": round(total, 2),
        "total_annual_savings": round(total * 12, 2),
        "by_category": by_cat,
    }


def budget_attention(usage: Dict[str, Any]) -> List[str]:
    """Flags for the spending-vs-limit picture."""
    notes: List[str] = []
    util = usage.get("utilizationPercentage")
    if isinstance(util, (int, float)):
        if util >= 100:
            notes.append("The monthly spending limit has been reached.")
        elif util >= 80:
            notes.append(f"Spending is at {round(util, 1)}% of the monthly limit.")
    daily, daily_limit = usage.get("dailySpending"), usage.get("dailySpendingLimit")
    if (isinstance(daily, (int, float)) and isinstance(daily_limit, (int, float))
            and daily_limit > 0 and daily >= daily_limit):
        notes.append("The daily spending limit has been reached.")
    return notes


def month_over_month(stats: Dict[str, Any]) -> Optional[float]:
    """Percent change of this month against last month, or None when there is no basis."""
    this, last = stats.get("thisMonth"), stats.get("lastMonth")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (this, last)) or last <= 0:
        return None
    return round((this - last) / last * 100, 1)

"""JSON formatting dimension benchmarks (medium)."""

from __future__ import annotations

from typing import Any

from pilotcode.utils.model_client import Message

from .base import BenchmarkResult, _call_llm, _extract_json


async def test_json_schema_compliance() -> BenchmarkResult:
    """Test deeply nested JSON schema with mixed types and edge values."""
    prompt = """You are an API engineer. A client needs the following data structure. Output it as a single valid JSON object (no markdown, no explanation).

Company profile schema (all fields required, exact structure):
{
  "company": {
    "name": "Acme Corp",
    "founded": 1998,
    "is_public": false,
    "metadata": {
      "tags": ["saas", "ai", "startup"],
      "settings": {
        "theme": "dark",
        "notifications": {
          "email": true,
          "sms": false,
          "push": {"enabled": true, "priority": "high"}
        }
      }
    },
    "departments": [
      {
        "name": "Engineering",
        "budget": 1250000.50,
        "headcount": 42,
        "teams": [
          {"id": "backend", "lead": "Alice", "size": 12, "skills": ["Python", "Go", "Rust"]},
          {"id": "frontend", "lead": "Bob", "size": 8, "skills": ["React", "TypeScript"]}
        ]
      },
      {
        "name": "Sales",
        "budget": 850000.00,
        "headcount": 18,
        "teams": [
          {"id": "enterprise", "lead": "Carol", "size": 6, "skills": ["Negotiation", "CRM"]}
        ]
      }
    ]
  }
}

Rules:
- Preserve exact nesting depth (company → departments → teams).
- budget fields must be numbers (not strings).
- headcount and size must be integers.
- skills arrays must contain strings.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.1,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="json_schema_compliance",
            dimension="json_formatting",
            sub_dimension="schema_compliance",
            score=0.0,
            raw_output=raw[:400],
            error="No valid JSON",
        )

    checks: dict[str, bool] = {}
    try:
        company = data.get("company", {})
        checks["has_company"] = isinstance(company, dict)
        checks["name_str"] = isinstance(company.get("name"), str)
        checks["founded_int"] = isinstance(company.get("founded"), int)
        checks["is_public_bool"] = isinstance(company.get("is_public"), bool)

        meta = company.get("metadata", {})
        checks["meta_tags_list"] = isinstance(meta.get("tags"), list)
        settings = meta.get("settings", {})
        notif = settings.get("notifications", {})
        checks["notif_nested"] = isinstance(notif.get("push"), dict)
        checks["push_priority_str"] = isinstance(notif.get("push", {}).get("priority"), str)

        depts = company.get("departments", [])
        checks["depts_list"] = isinstance(depts, list) and len(depts) >= 2
        if depts:
            d0 = depts[0]
            checks["budget_num"] = isinstance(d0.get("budget"), (int, float))
            checks["headcount_int"] = isinstance(d0.get("headcount"), int)
            teams = d0.get("teams", [])
            checks["teams_list"] = isinstance(teams, list) and len(teams) >= 1
            if teams:
                checks["skills_str_list"] = all(
                    isinstance(s, str) for s in teams[0].get("skills", [])
                )
    except Exception:
        checks["exception"] = False

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = passed / total if total else 0.0

    return BenchmarkResult(
        test_name="json_schema_compliance",
        dimension="json_formatting",
        sub_dimension="schema_compliance",
        score=score,
        raw_output=raw[:400],
        metadata={"checks": checks, "passed": passed, "total": total},
    )


async def test_json_self_correction() -> BenchmarkResult:
    """Test fixing a deeply nested malformed JSON."""
    prompt1 = """Output the following object EXACTLY as shown (it is intentionally malformed):

{
  "config": {
    "database": {
      "host": "localhost",
      "port": 5432,
      "pool": {
        "min": 5,
        "max": 20
        "timeout": 30
      }
    },
    "cache": {
      "enabled": true,
      "ttl": 300,
    }
  }
}

Notice the missing comma after `"max": 20` and the trailing comma after `"ttl": 300`. Output EXACTLY as shown.
"""
    raw1 = await _call_llm(
        [Message(role="user", content=prompt1)],
        temperature=0.1,
    )

    prompt2 = f"""The following text is malformed JSON. Fix ALL syntax errors and output valid JSON only:

{raw1}
"""
    raw2 = await _call_llm(
        [Message(role="user", content=prompt2)],
        temperature=0.1,
    )

    data = _extract_json(raw2)
    is_valid = False
    structure_ok = False
    if data is not None and isinstance(data, dict):
        config = data.get("config", {})
        db = config.get("database", {})
        pool = db.get("pool", {})
        cache = config.get("cache", {})
        structure_ok = (
            db.get("host") == "localhost"
            and db.get("port") == 5432
            and pool.get("min") == 5
            and pool.get("max") == 20
            and pool.get("timeout") == 30
            and cache.get("enabled") is True
            and cache.get("ttl") == 300
        )
        is_valid = True

    score = 1.0 if is_valid and structure_ok else 0.5 if is_valid else 0.0
    return BenchmarkResult(
        test_name="json_self_correction",
        dimension="json_formatting",
        sub_dimension="self_correction",
        score=score,
        raw_output=raw2[:400],
        metadata={"corrected": is_valid, "structure_ok": structure_ok},
    )


async def test_json_in_complex_context() -> BenchmarkResult:
    """Test JSON output after multi-step financial reasoning."""
    prompt = """A SaaS company has the following Q3 financials:
- MRR (Monthly Recurring Revenue): $125,000
- Gross Margin: 78%
- Monthly Churn Rate: 4%
- Customer Acquisition Cost (CAC): $450
- Average Revenue Per User (ARPU): $250/month

Calculate and output ONLY valid JSON with these exact fields:
{
  "annual_revenue_run_rate": <number>,
  "gross_profit_monthly": <number>,
  "customer_lifetime_months": <number>,
  "customer_lifetime_value": <number>,
  "ltv_cac_ratio": <number>,
  "recommendation": "brief strategic recommendation (one sentence)"
}

Calculations:
- annual_revenue_run_rate = MRR * 12
- gross_profit_monthly = MRR * gross_margin
- customer_lifetime_months = 1 / monthly_churn_rate
- customer_lifetime_value = ARPU * gross_margin * customer_lifetime_months
- ltv_cac_ratio = customer_lifetime_value / CAC
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="json_in_complex_context",
            dimension="json_formatting",
            sub_dimension="valid_json_rate",
            score=0.0,
            raw_output=raw[:400],
            error="No valid JSON",
        )

    expected = {
        "annual_revenue_run_rate": 1_500_000,
        "gross_profit_monthly": 97_500,
        "customer_lifetime_months": 25,
        "customer_lifetime_value": 4_875,
        "ltv_cac_ratio": 10.833333,
    }

    checks: dict[str, bool] = {}
    for key, exp_val in expected.items():
        actual = data.get(key)
        if isinstance(actual, (int, float)) and isinstance(exp_val, (int, float)):
            checks[key] = abs(actual - exp_val) < 1
        else:
            checks[key] = False

    has_recommendation = bool(data.get("recommendation"))
    checks["has_recommendation"] = has_recommendation

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = passed / total if total else 0.0

    return BenchmarkResult(
        test_name="json_in_complex_context",
        dimension="json_formatting",
        sub_dimension="valid_json_rate",
        score=score,
        raw_output=raw[:400],
        metadata={"checks": checks, "passed": passed, "total": total},
    )

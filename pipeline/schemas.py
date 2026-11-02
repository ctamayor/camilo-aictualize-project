"""JSON schemas for what each agent must return.

Claude Code validates an agent's reply against its schema before the pipeline
sees it, so malformed output never reaches the validation or scoring steps.
Values are free text apart from message ids; later steps classify them.
"""


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


CITATION = _obj({"message": {"type": "string"}, "quote": {"type": "string"}})
NOTED = _obj({"message": {"type": "string"}, "quote": {"type": "string"}, "note": {"type": "string"}})

SCOUT = _obj({
    "patterns": {"type": "array", "items": _obj({
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "occurrences": {"type": "array", "items": CITATION},
        "observations": {"type": "array", "items": NOTED},
        "stalls": {"type": "array", "items": NOTED},
    })},
    "untrusted": {"type": "array", "items": _obj({
        "message": {"type": "string"},
        "quote": {"type": "string"},
        "reason": {"type": "string"},
    })},
})

MERGE = _obj({
    "processes": {"type": "array", "items": _obj({
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "patterns": {"type": "array", "items": {"type": "string"}},
    })},
})

# The change comes first, then the unit and evidence, the reasoning, and the number last.
ESTIMATE = _obj({
    "estimates": {"type": "array", "items": _obj({
        "process": {"type": "string"},
        "change": {"type": "string"},
        "explanation": {"type": "string"},
        "not_served": {"type": "array", "items": {"type": "string"}},
        "ongoing": {"type": "boolean"},
        "stated_rate": _obj({"per_month": {"type": "number"}, "quote": {"type": "string"}, "words": {"type": "string"}}),
        "basis": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
        "minutes": {"type": "number"},
    })},
})

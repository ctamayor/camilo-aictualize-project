"""JSON schemas for what each worker agent must return.

Claude Code validates an agent's reply against its schema before the pipeline
sees it, so malformed output never reaches the steps that use it. Values are
free text apart from message files, which the code checks.
"""


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


READER = _obj({
    "leads": {"type": "array", "items": _obj({
        "work": {"type": "string"},
        "why": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
    })},
})

DRAFT = _obj({
    "kind": {"type": "string"},
    "audience": {"type": "string"},
    "title": {"type": "string"},
    "body": {"type": "string"},
})

"""Portable JSON Schema contracts, shared by runtime validation and exported schema.json."""

TEXT = {"type": "string", "minLength": 1}
DATE = {"type": "string", "format": "date"}
NULL_DATE = {"anyOf": [DATE, {"type": "null"}]}
STRINGS = {"type": "array", "items": TEXT, "uniqueItems": True}
INTERVAL = {
    "type": "object",
    "required": ["from", "until"],
    "properties": {"from": DATE, "until": DATE},
    "additionalProperties": False,
}


def contract(properties, required=None):
    return {
        "type": "object",
        "required": required or list(properties),
        "properties": properties,
        "additionalProperties": True,
    }


SOURCE = contract(
    {
        "source_family_id": TEXT,
        "title": TEXT,
        "publisher": TEXT,
        "url": {"anyOf": [{"type": "string", "format": "uri"}, {"type": "null"}]},
        "language": TEXT,
        "jurisdiction": TEXT,
        "publication_date": NULL_DATE,
        "retrieved_at": {"type": "string", "format": "date-time"},
        "acquisition_status": {"enum": ["acquired", "reference_only"]},
        "use_terms_status": TEXT,
        "source_kind": TEXT,
    }
)
SOURCE["properties"].update(
    {
        "original_path": TEXT,
        "content_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "document_fixture_id": TEXT,
        "version_fixture_id": TEXT,
        "mime": TEXT,
        "size": {"type": "integer", "minimum": 1},
        "synthetic": {"type": "boolean"},
        "scenario_family_id": {"type": ["string", "null"]},
        "metadata": {"type": "object"},
    }
)
SOURCE["allOf"] = [
    {
        "if": {"properties": {"acquisition_status": {"const": "acquired"}}},
        "then": {"required": ["original_path", "content_sha256"]},
        "else": {
            "not": {"anyOf": [{"required": ["original_path"]}, {"required": ["content_sha256"]}]}
        },
    }
]
FACT = contract({"fact_id": TEXT, "kind": {"enum": ["synthetic", "industry"]}, "text": TEXT})
FACT["properties"].update(
    {
        "value": {"type": "number"},
        "unit": TEXT,
        "public_source": TEXT,
        "synthetic": {"type": "boolean"},
    }
)
FACT["allOf"] = [
    {
        "if": {"required": ["value"]},
        "then": {"required": ["unit", "synthetic"], "properties": {"synthetic": {"const": True}}},
    },
    {
        "if": {"properties": {"kind": {"const": "industry"}}},
        "then": {"required": ["public_source"]},
    },
    {
        "if": {"properties": {"kind": {"const": "synthetic"}}},
        "then": {"properties": {"text": {"pattern": "模拟"}}},
    },
]
SCENARIO = contract(
    {
        "scenario_family_id": TEXT,
        "synthetic": {"const": True},
        "store_fixture": TEXT,
        "entity_refs": STRINGS,
        "effective_interval": INTERVAL,
        "facts": {"type": "array", "minItems": 1, "items": FACT},
        "exceptions": STRINGS,
        "document_kinds": {
            "type": "array",
            "minItems": 1,
            "items": {"enum": ["supplier", "product", "sop", "campaign", "retro"]},
        },
    }
)
CASE = contract(
    {
        "case_id": TEXT,
        "split": {"enum": ["dev", "test"]},
        "scenario_family_id": TEXT,
        "group": {
            "enum": ["exact", "keyword", "semantic", "cross_document", "unanswerable", "hybrid"]
        },
        "query": TEXT,
        "store_fixture": TEXT,
        "as_of": DATE,
        "required_evidence": {
            "type": "array",
            "items": {"type": "array", "minItems": 1, "uniqueItems": True, "items": TEXT},
        },
        "forbidden_claims": STRINGS,
        "business_tools": STRINGS,
        "relation_tags": STRINGS,
    }
)
SCENARIO["properties"].update(
    {
        "scenario_id": TEXT,
        "supplier_fixture_id": TEXT,
        "sku_fixture_ids": STRINGS,
        "author": TEXT,
        "generation_method": TEXT,
        "generation_input_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    }
)
CASE["properties"].update(
    {
        "scenario_id": TEXT,
        "source_family_ids": STRINGS,
        "entry_entities": STRINGS,
        "query_constraints": {"type": "object"},
        "missing_conditions": STRINGS,
        "expected_behavior": TEXT,
        "gold_status": TEXT,
    }
)
MACHINE_CONDITIONS = {
    "type": "object",
    "minProperties": 1,
    "maxProperties": 30,
    "propertyNames": {"type": "string", "minLength": 1, "maxLength": 128},
    "additionalProperties": {"type": ["string", "boolean", "integer", "number"]},
}
RELATION = contract(
    {
        "relation_id": TEXT,
        "from_entity": TEXT,
        "to_entity": TEXT,
        "relation_type": TEXT,
        "source_version_id": TEXT,
        "locator": TEXT,
        "evidence_id": TEXT,
        "conditions": STRINGS,
        "effective_interval": INTERVAL,
        "assertion_status": {"const": "synthetic_verified"},
        "machine_conditions": MACHINE_CONDITIONS,
        "evidence_quote": {"type": ["string", "null"]},
        "evidence_chunk_ids": {"type": "array", "maxItems": 0},
        "executable": {"const": False},
        "execution_status": TEXT,
        "retrieval_orientation": TEXT,
        "retrieval_edges": {"type": "array", "items": {"type": "object"}},
    }
)
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$defs": {
        "source": SOURCE,
        "scenario": SCENARIO,
        "case": CASE,
        "fact": FACT,
        "effective_interval": INTERVAL,
        "relation": RELATION,
        "machine_conditions": MACHINE_CONDITIONS,
    },
    "oneOf": [{"$ref": "#/$defs/source"}, {"$ref": "#/$defs/scenario"}, {"$ref": "#/$defs/case"}],
}

"""Small stdlib JSON Schema validator for tool arguments (no jsonschema dependency).

Supported keywords: type (name or list), enum, minimum, maximum, minLength, maxLength, minItems,
maxItems, required, properties, additionalProperties (False only), items. Anything else is ignored.
`validate()` returns None when the value is valid, else one short error message with the path.
"""
import math

MAX_DEPTH = 8


def _is_type(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and not (isinstance(value, float) and (math.isnan(value) or math.isinf(value))))
    return True  # unknown type name: do not reject


def validate(value, schema, path="args", _depth=0):
    """Return None if `value` fits `schema`, else an error string."""
    if not isinstance(schema, dict) or _depth > MAX_DEPTH:
        return None
    t = schema.get("type")
    if t is not None:
        names = t if isinstance(t, list) else [t]
        if not any(_is_type(value, n) for n in names):
            return "%s must be of type %s" % (path, "/".join(str(n) for n in names))
    if "enum" in schema and value not in schema["enum"]:
        return "%s must be one of %s" % (path, ", ".join(repr(e) for e in schema["enum"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return "%s must be >= %s" % (path, schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            return "%s must be <= %s" % (path, schema["maximum"])
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return "%s is longer than %s characters" % (path, schema["maxLength"])
        if "minLength" in schema and len(value) < schema["minLength"]:
            return "%s is shorter than %s characters" % (path, schema["minLength"])
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return "%s has more than %s items" % (path, schema["maxItems"])
        if "minItems" in schema and len(value) < schema["minItems"]:
            return "%s has fewer than %s items" % (path, schema["minItems"])
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                err = validate(item, item_schema, "%s[%d]" % (path, i), _depth + 1)
                if err:
                    return err
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                return "%s is missing required field '%s'" % (path, key)
        props = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    return "%s has unknown field '%s'" % (path, key)
        for key, sub in props.items():
            if key in value:
                err = validate(value[key], sub, "%s.%s" % (path, key), _depth + 1)
                if err:
                    return err
    return None

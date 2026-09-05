"""Small, deterministic condition evaluator for Policy.conditions JSON.

Supports only a fixed set of comparison operators over a structured
{"all": [...]} / {"any": [...]} tree of {"field", "operator", "value"}
leaves. There is no code evaluation of any kind: no eval(), no exec(),
no user-supplied Python, no SQL. Unknown shapes fail closed by raising
PolicyConditionError, which callers must treat as BLOCK.
"""

from decimal import Decimal, InvalidOperation
from typing import Any


class PolicyConditionError(Exception):
    pass


def _resolve_field(field: str, context: dict[str, Any]) -> Any:
    if not isinstance(field, str) or not field:
        raise PolicyConditionError(f"Invalid field reference: {field!r}")
    value: Any = context
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise PolicyConditionError(f"Missing field '{field}' in evaluation context")
        value = value[part]
    return value


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PolicyConditionError(f"Cannot compare non-numeric value: {value!r}") from exc


def _eq(actual: Any, expected: Any) -> bool:
    try:
        return _as_decimal(actual) == _as_decimal(expected)
    except PolicyConditionError:
        return actual == expected


def _neq(actual: Any, expected: Any) -> bool:
    return not _eq(actual, expected)


def _in(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple, set)):
        raise PolicyConditionError(f"'in' operator requires a list value, got {expected!r}")
    return actual in expected


OPERATORS = {
    "eq": _eq,
    "neq": _neq,
    "lt": lambda a, b: _as_decimal(a) < _as_decimal(b),
    "lte": lambda a, b: _as_decimal(a) <= _as_decimal(b),
    "gt": lambda a, b: _as_decimal(a) > _as_decimal(b),
    "gte": lambda a, b: _as_decimal(a) >= _as_decimal(b),
    "in": _in,
}


def evaluate_conditions(conditions: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    if not conditions:
        return True
    return _evaluate_node(conditions, context)


def _evaluate_node(node: Any, context: dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        raise PolicyConditionError(f"Malformed policy condition node: {node!r}")

    if "all" in node:
        clauses = node["all"]
        if not isinstance(clauses, list):
            raise PolicyConditionError("'all' must be a list of conditions")
        return all(_evaluate_node(clause, context) for clause in clauses)

    if "any" in node:
        clauses = node["any"]
        if not isinstance(clauses, list):
            raise PolicyConditionError("'any' must be a list of conditions")
        return any(_evaluate_node(clause, context) for clause in clauses)

    return _evaluate_leaf(node, context)


def _evaluate_leaf(leaf: dict[str, Any], context: dict[str, Any]) -> bool:
    missing = {"field", "operator", "value"} - leaf.keys()
    if missing:
        raise PolicyConditionError(f"Malformed policy condition, missing keys: {sorted(missing)}")

    operator = leaf["operator"]
    op_fn = OPERATORS.get(operator)
    if op_fn is None:
        raise PolicyConditionError(f"Unsupported policy operator: {operator!r}")

    actual = _resolve_field(leaf["field"], context)
    return op_fn(actual, leaf["value"])

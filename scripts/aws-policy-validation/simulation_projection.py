"""Conservative exact-action statement projection, not a policy evaluator.

Only a plain exact Action selector can prove a statement irrelevant. Everything
else stays in the request; resource matching and conditions are left to AWS.
The verifier independently checks the ordered partition against the originals.
"""

import copy
import hashlib
import json
import re


METHOD = "exact-action-statements-v1"
EXACT_ACTION = re.compile(r"[A-Za-z0-9-]+:[A-Za-z0-9]+")


def _require(condition, message):
  if not condition:
    raise ValueError(message)


def _canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"),
      ensure_ascii=True, allow_nan=False)


def content_sha256(value):
  """Hash JSON content without relying on input dictionary key order."""
  return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sources(sources, action):
  _require(isinstance(action, str) and EXACT_ACTION.fullmatch(action),
      "The tested action must be a plain exact IAM action.")
  _require(isinstance(sources, dict) and sources and all(
      isinstance(identifier, str) and identifier for identifier in sources),
      "Projection requires named original policy documents.")
  for document in sources.values():
    _require(isinstance(document, dict) and isinstance(document.get("Statement"), list)
        and document["Statement"], "Original policy must contain statements.")
    for statement in document["Statement"]:
      _require(isinstance(statement, dict) and statement.get("Effect") in {"Allow", "Deny"},
          "Unsupported or malformed original policy statement.")
    _canonical(document)


def project_policies(sources, action):
  """Keep whole matching or uncertain statements; never inspect condition values."""
  _sources(sources, action)
  projected = {}
  for identifier, document in sources.items():
    kept = []
    for statement in document["Statement"]:
      selector = statement.get("Action")
      selectors = [selector] if isinstance(selector, str) else selector
      exact = ("NotAction" not in statement and isinstance(selectors, list)
          and bool(selectors) and all(isinstance(value, str)
            and EXACT_ACTION.fullmatch(value) for value in selectors))
      if not exact or action.casefold() in {value.casefold() for value in selectors}:
        kept.append(copy.deepcopy(statement))
    if kept:
      result = copy.deepcopy(document)
      result["Statement"] = kept
      projected[identifier] = result
  return projected


def verify_projection(sources, action, projected):
  """Independently verify each retained statement and each omission.

  This does not call the projector or reuse its classification result. A cursor
  walks candidate statements in original order. Each skipped original must have
  a demonstrably nonmatching exact selector; every other original must appear
  byte-for-byte in canonical JSON, including Allow/Deny, resources and conditions.
  """
  _sources(sources, action)
  _require(isinstance(projected, dict) and set(projected) <= set(sources),
      "Projection contains an unreviewed policy identity.")
  retained = omitted = 0
  for identifier, original in sources.items():
    candidate = projected.get(identifier)
    if candidate is not None:
      _require(isinstance(candidate, dict) and isinstance(candidate.get("Statement"), list)
          and candidate["Statement"], "Projected policies must have nonempty statements.")
      _require(_canonical({key: value for key, value in candidate.items() if key != "Statement"}) ==
          _canonical({key: value for key, value in original.items() if key != "Statement"}),
          "Projection changed original policy metadata.")
    proposed = candidate["Statement"] if candidate is not None else []
    cursor = 0
    for statement in original["Statement"]:
      # An omission certificate is valid only for an entirely plain Action
      # selector. Unknown selectors cannot establish an absent-action proof.
      can_omit = False
      if "Action" in statement and "NotAction" not in statement:
        raw = statement["Action"]
        if isinstance(raw, str):
          can_omit = bool(EXACT_ACTION.fullmatch(raw)) and raw.casefold() != action.casefold()
        elif isinstance(raw, list) and raw:
          can_omit = all(isinstance(item, str) and EXACT_ACTION.fullmatch(item)
              and item.casefold() != action.casefold() for item in raw)
      if can_omit:
        omitted += 1
        continue
      _require(cursor < len(proposed) and _canonical(proposed[cursor]) == _canonical(statement),
          "Projection dropped or changed a matching/uncertain Allow or Deny statement.")
      cursor += 1
      retained += 1
    _require(cursor == len(proposed), "Projection added, duplicated or retained an irrelevant statement.")
    _require(bool(proposed) == (identifier in projected),
        "Empty projected policies must be omitted, not submitted to AWS.")
  return {
    "method": METHOD,
    "action": action,
    "source_sha256": {identifier: content_sha256(document) for identifier, document in sources.items()},
    "projected_sha256": {identifier: content_sha256(document) for identifier, document in projected.items()},
    "retained_statement_count": retained,
    "omitted_statement_count": omitted,
  }

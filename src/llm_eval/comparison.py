"""Audit model-generated comparison rows against the fixed vehicle list."""


COMPARISON_FIELDS = (
    "source_id", "model", "trim", "year", "price_wan", "energy", "seats", "adas"
)


def audit_parameter_comparison(payload, vehicle_data):
    comparisons = payload.get("parameter_comparison")
    candidates = payload.get("candidate_cars")
    if not isinstance(comparisons, list):
        return ["parameter_comparison is not an array"]
    if not isinstance(candidates, list):
        return ["candidate_cars is not an array"]

    vehicles_by_identity = {}
    for vehicle in vehicle_data:
        key = (vehicle["model"], vehicle["trim"], vehicle["year"])
        vehicles_by_identity.setdefault(key, []).append(vehicle)

    expected = {}
    issues = []
    for index, candidate in enumerate(candidates):
        key = (candidate.get("model"), candidate.get("trim"), candidate.get("year"))
        matches = vehicles_by_identity.get(key, [])
        if len(matches) != 1:
            issues.append("candidate_cars[{}] does not identify one fixed vehicle".format(index))
            continue
        vehicle = matches[0]
        if candidate.get("evidence_ids") != [vehicle["source_id"]]:
            issues.append(
                "candidate_cars[{}] must cite the matching source_id {}".format(
                    index, vehicle["source_id"]
                )
            )
        expected[vehicle["source_id"]] = vehicle

    actual = {}
    for index, row in enumerate(comparisons):
        if not isinstance(row, dict):
            issues.append("parameter_comparison[{}] is not an object".format(index))
            continue
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            issues.append("parameter_comparison[{}] has no source_id".format(index))
            continue
        if source_id in actual:
            issues.append("duplicate comparison source_id: {}".format(source_id))
            continue
        actual[source_id] = row

    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            issues.append("missing comparison rows: {}".format(", ".join(missing)))
        if extra:
            issues.append("unexpected comparison rows: {}".format(", ".join(extra)))

    for source_id in sorted(set(actual) & set(expected)):
        row = actual[source_id]
        vehicle = expected[source_id]
        mismatched = [
            field for field in COMPARISON_FIELDS
            if row.get(field) != vehicle.get(field)
            or type(row.get(field)) is not type(vehicle.get(field))
        ]
        if mismatched:
            issues.append("{} differs from fixed data: {}".format(source_id, ", ".join(mismatched)))
    return issues

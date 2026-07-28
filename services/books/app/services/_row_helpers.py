import json
import typing


def json_agg_list(raw: typing.Any) -> typing.List[typing.Any]:
    """Normalize a Postgres `json_agg(...)` column: the driver returns it as a
    JSON string, already-parsed list, or None depending on the query shape."""
    if isinstance(raw, str):
        return json.loads(raw)
    if raw is None:
        return []
    return raw

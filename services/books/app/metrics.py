import opentelemetry.metrics as metrics_api

_meter = metrics_api.get_meter(__name__)
_search_requests = _meter.create_counter(
    "search_requests",
    description="Search and autocomplete requests by kind and whether any result was returned",
)


def record_search(kind: str, has_results: bool) -> None:
    _search_requests.add(
        1, {"kind": kind, "has_results": "true" if has_results else "false"}
    )

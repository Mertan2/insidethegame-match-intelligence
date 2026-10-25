"""Production tracing with OpenTelemetry, exported to Azure Application Insights.

Off unless APPLICATIONINSIGHTS_CONNECTION_STRING is set, and never allowed to break the app:
every span is best effort. Spans cover what matters for running the agent team in production:
each narration, each agent step (path taken, fallback, latency), each Ask question and the tools
it called, and each voice request. Calls to Azure OpenAI and Azure Speech are traced as
dependencies, and HTTP requests as requests (a live WebSocket is one request for the whole
connection, not one per message). Microsoft Agent Framework adds its own workflow and
invoke_agent spans under each narration.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace

log = logging.getLogger(__name__)
tracer = trace.get_tracer("insidethegame")
enabled = False


def setup() -> bool:
    """Start exporting to Application Insights if configured. Returns whether tracing is on."""
    global enabled
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn or enabled:
        return enabled
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        os.environ.setdefault("OTEL_SERVICE_NAME", "insidethegame")
        configure_azure_monitor(connection_string=conn)
        enabled = True
    except Exception as exc:  # noqa: BLE001 - observability must never stop the app
        log.warning("Tracing disabled: %s", exc)
    return enabled


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """A span with attributes; None values are dropped, everything else stringified if needed."""
    with tracer.start_as_current_span(name) as s:
        for key, value in attributes.items():
            if value is None:
                continue
            s.set_attribute(key, value if isinstance(value, (str, bool, int, float)) else str(value))
        yield s

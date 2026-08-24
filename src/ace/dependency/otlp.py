from typing import Any

from fastapi import APIRouter, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from ace.dependency.extractor import process_spans

router = APIRouter()


@router.post("/v1/traces")
async def receive_traces(request: Request) -> Any:
    """
    Receives OTLP protobuf traces from the OpenTelemetry Collector.
    Returns 200 immediately (as expected by the collector).
    """
    body = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        import gzip

        body = gzip.decompress(body)

    # Decode the protobuf message
    req = ExportTraceServiceRequest()
    try:
        req.ParseFromString(body)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to parse traces: {e}")
        # If parsing fails, just return 200 to not block the collector
        return Response(status_code=200)

    # Process spans synchronously
    process_spans(req)

    return Response(status_code=200)

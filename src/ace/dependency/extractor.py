import logging
from datetime import UTC, datetime
from uuid import UUID

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from prometheus_client import Counter

from ace.api.deps import SessionLocal
from ace.config import settings
from ace.db.models.components import Dependency
from ace.ingestion.models import Candidate
from ace.ingestion.resolver import Resolver

logger = logging.getLogger(__name__)

map_resolution_miss_count = Counter(
    "ace_map_resolution_miss_count", "Number of trace span endpoints that could not be resolved"
)


def process_spans(request: ExportTraceServiceRequest) -> None:
    """
    Extracts dependency edges from a batch of OTLP spans.
    Parent -> Child span relationships mean Parent DEPENDS ON Child.
    """
    with SessionLocal() as db:
        resolver = Resolver(db)

        edges_to_upsert: dict[tuple[UUID, UUID], bool] = {}

        for resource_span in request.resource_spans:
            service_name = None
            for attr in resource_span.resource.attributes:
                if attr.key == "service.name":
                    service_name = attr.value.string_value
                    break

            if not service_name:
                continue

            # Resolve the service name to a component ID
            candidates = [Candidate(value=service_name, field_name="service.name")]
            if ":" in service_name:
                candidates.append(
                    Candidate(value=service_name.split(":")[0], field_name="service.name_no_port")
                )

            from_component_id, _ = resolver.resolve(candidates, source_tool="trace")
            if not from_component_id:
                logger.warning(
                    f"UNRESOLVED TRACE: Could not resolve component for service: {service_name}"
                )
                map_resolution_miss_count.inc()
                # If we can't resolve the dependent, we can't create an edge
                continue

            for scope_span in resource_span.scope_spans:
                for span in scope_span.spans:
                    # 1. Check for peer attributes first (datastore edges)
                    peer_service = None
                    for attr in span.attributes:
                        if attr.key in (
                            "db.system",
                            "db.name",
                            "net.peer.name",
                            "peer.service",
                            "server.address",
                            "network.peer.address",
                        ):
                            peer_service = attr.value.string_value
                            break
                        elif attr.key in ("http.url", "url.full"):
                            # Extract host:port from http://host:port/path
                            val = attr.value.string_value
                            if "://" in val:
                                peer_service = val.split("://")[1].split("/")[0]
                            break

                    if peer_service:
                        peer_candidates = [Candidate(value=peer_service, field_name="peer_service")]
                        if ":" in peer_service:
                            peer_candidates.append(
                                Candidate(
                                    value=peer_service.split(":")[0],
                                    field_name="peer_service_no_port",
                                )
                            )

                        to_component_id, _ = resolver.resolve(peer_candidates, source_tool="trace")
                        if to_component_id and from_component_id != to_component_id:
                            logger.info(
                                f"Adding trace edge from {from_component_id} to "
                                f"{to_component_id} ({peer_service})"
                            )
                            _add_edge(edges_to_upsert, from_component_id, to_component_id)
                        elif not to_component_id:
                            logger.warning(
                                f"UNRESOLVED PEER: Could not resolve peer attribute: {peer_service}"  # noqa: E501
                            )
                            map_resolution_miss_count.inc()

                    # 2. Extracting parent->child from span IDs is tricky across batches.
                    # By checking peer attributes for ALL client spans, we naturally cover both
                    # datastores and downstream services.

        # Upsert the collected edges
        now = datetime.now(UTC)
        for (from_id, to_id), _ in edges_to_upsert.items():
            existing = (
                db.query(Dependency)
                .filter_by(from_component_id=from_id, to_component_id=to_id)
                .first()
            )

            if existing:
                existing.observation_count += 1
                existing.last_seen = now
                existing.confidence = min(
                    settings.EDGE_CONFIDENCE_MAX,
                    existing.confidence + settings.EDGE_CONFIDENCE_BOOST,
                )
                existing.source = "trace"
            else:
                new_edge = Dependency(
                    from_component_id=from_id,
                    to_component_id=to_id,
                    confidence=settings.EDGE_CONFIDENCE_BOOST,
                    source="trace",
                    first_seen=now,
                    last_seen=now,
                    observation_count=1,
                )
                db.add(new_edge)

        if edges_to_upsert:
            db.commit()


def _add_edge(edges: dict[tuple[UUID, UUID], bool], from_id: UUID, to_id: UUID) -> None:
    edges[(from_id, to_id)] = True

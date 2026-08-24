import logging
import threading
from typing import Any
from uuid import UUID

import networkx as nx
from sqlalchemy.orm import Session

from ace.db.models.components import Dependency

logger = logging.getLogger(__name__)


class DependencyGraph:
    """
    Thread-safe singleton wrapping a NetworkX DiGraph.
    Edges are directed: from_component_id (dependent) -> to_component_id (dependency).
    This matches the semantics: Parent DEPENDS ON Child.
    """

    _instance: Any = None
    _lock = threading.Lock()
    _graph: Any
    _rw_lock: threading.RLock

    def __new__(cls) -> Any:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._graph = nx.DiGraph()
                cls._instance._rw_lock = threading.RLock()
            return cls._instance

    def refresh(self, session: Session) -> None:
        """
        Reloads all edges from the dependencies table into memory.
        Detects and logs cycles.
        """
        edges = session.query(Dependency).all()
        new_graph: Any = nx.DiGraph()

        for edge in edges:
            new_graph.add_edge(
                edge.from_component_id,
                edge.to_component_id,
                confidence=edge.confidence,
                source=edge.source,
            )

        with self._rw_lock:
            self._graph = new_graph

        try:
            cycles = list(nx.simple_cycles(self._graph))
            if cycles:
                logger.warning(f"Detected {len(cycles)} cycles in the dependency graph: {cycles}")
        except nx.NetworkXNoCycle:
            pass

    def neighbours_within(
        self, component_id: UUID, hops: int, direction: str = "both"
    ) -> set[UUID]:
        """
        Returns a set of component IDs within N hops.
        direction can be 'inbound', 'outbound', or 'both'.
        Cycle-safe because it tracks visited nodes.
        """
        if direction not in ("inbound", "outbound", "both"):
            raise ValueError("Direction must be inbound, outbound, or both")

        with self._rw_lock:
            if component_id not in self._graph:
                return set()

            visited = set()
            queue = [(component_id, 0)]

            while queue:
                current_node, current_hop = queue.pop(0)

                if current_node not in visited:
                    visited.add(current_node)

                    if current_hop < hops:
                        neighbors: set[UUID] = set()
                        if direction in ("outbound", "both"):
                            neighbors.update(self._graph.successors(current_node))
                        if direction in ("inbound", "both"):
                            neighbors.update(self._graph.predecessors(current_node))

                        for neighbor in neighbors:
                            if neighbor not in visited:
                                queue.append((neighbor, current_hop + 1))

            return visited

    def dependents_of(self, component_id: UUID) -> set[UUID]:
        """
        Returns all components that recursively depend on this component.
        Since edges are A DEPENDS ON B, dependents of B are predecessors.
        """
        with self._rw_lock:
            if component_id not in self._graph:
                return set()
            # reverse() returns a view where edges point from B to A
            return set(nx.descendants(self._graph.reverse(copy=False), component_id))

    def dependencies_of(self, component_id: UUID) -> set[UUID]:
        """
        Returns all components this component recursively depends on.
        Since edges are A DEPENDS ON B, dependencies of A are successors.
        """
        with self._rw_lock:
            if component_id not in self._graph:
                return set()
            return set(nx.descendants(self._graph, component_id))

    def shortest_path(self, source: UUID, target: UUID) -> list[UUID]:
        """
        Shortest undirected path between two components.
        """
        with self._rw_lock:
            if source not in self._graph or target not in self._graph:
                return []
            try:
                # Undirected path means treating the graph as undirected
                undirected = self._graph.to_undirected(as_view=True)
                return nx.shortest_path(undirected, source=source, target=target)
            except nx.NetworkXNoPath:
                return []

    def get_edge_data(self, u: UUID, v: UUID) -> Any:
        with self._rw_lock:
            if self._graph.has_edge(u, v):
                return self._graph.get_edge_data(u, v)
            return None

    def get_node_count(self) -> int:
        with self._rw_lock:
            return int(self._graph.number_of_nodes())

    def get_edge_count(self) -> int:
        with self._rw_lock:
            return int(self._graph.number_of_edges())


graph_instance = DependencyGraph()

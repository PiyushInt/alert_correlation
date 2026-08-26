import logging
from typing import Protocol
from uuid import UUID

import networkx as nx
import pyroaring

from ace.config import settings
from ace.dependency.graph import DependencyGraph, graph_instance

logger = logging.getLogger(__name__)


class Reachability(Protocol):
    def get_shortest_path(self, source: UUID, target: UUID) -> tuple[int, str, list[UUID]] | None:
        """
        Returns (hops, direction, path) if reachable within MAX_INCIDENT_HOPS, else None.
        Direction is "outbound" (source depends on target), "inbound" (target depends on source),
        or "undirected" (path exists but mixes directions).
        """
        ...


class NetworkXReachability:
    def __init__(self, graph: DependencyGraph) -> None:
        self.graph = graph

    def get_shortest_path(self, source: UUID, target: UUID) -> tuple[int, str, list[UUID]] | None:
        if source == target:
            return (0, "self", [source])

        with self.graph._rw_lock:
            g = self.graph._graph
            if source not in g or target not in g:
                return None

            max_hops = settings.MAX_INCIDENT_HOPS

            # Try outbound (source depends on target - path from source to target)
            try:
                out_path = nx.shortest_path(g, source=source, target=target)
                if len(out_path) - 1 <= max_hops:
                    return (len(out_path) - 1, "outbound", out_path)
            except nx.NetworkXNoPath:
                pass

            # Try inbound (target depends on source - path from target to source)
            try:
                in_path = nx.shortest_path(g, source=target, target=source)
                if len(in_path) - 1 <= max_hops:
                    return (len(in_path) - 1, "inbound", list(reversed(in_path)))
            except nx.NetworkXNoPath:
                pass

            # Try undirected
            try:
                undir_g = g.to_undirected(as_view=True)
                undir_path = nx.shortest_path(undir_g, source=source, target=target)
                if len(undir_path) - 1 <= max_hops:
                    return (len(undir_path) - 1, "undirected", undir_path)
            except nx.NetworkXNoPath:
                pass

            return None


class BitmapReachability:
    def __init__(self, graph: DependencyGraph) -> None:
        self.graph = graph
        self.uuid_to_int: dict[UUID, int] = {}
        self.int_to_uuid: dict[int, UUID] = {}
        self.outbound_bitmaps: dict[int, pyroaring.BitMap] = {}
        self.inbound_bitmaps: dict[int, pyroaring.BitMap] = {}
        self.undirected_bitmaps: dict[int, pyroaring.BitMap] = {}
        self._build_bitmaps()

    def _build_bitmaps(self) -> None:
        with self.graph._rw_lock:
            g = self.graph._graph

            # Create mapping
            for idx, node in enumerate(g.nodes):
                self.uuid_to_int[node] = idx
                self.int_to_uuid[idx] = node

            # Initialize bitmaps for up to MAX_INCIDENT_HOPS
            max_hops = settings.MAX_INCIDENT_HOPS
            undir_g = g.to_undirected(as_view=True)

            for node in g.nodes:
                u_idx = self.uuid_to_int[node]

                # Outbound
                out_bm = pyroaring.BitMap()
                for target, length in nx.single_source_shortest_path_length(
                    g, node, cutoff=max_hops
                ).items():
                    if length > 0:
                        out_bm.add(self.uuid_to_int[target])
                self.outbound_bitmaps[u_idx] = out_bm

                # Inbound
                in_bm = pyroaring.BitMap()
                # Target depends on source -> path from target to node
                # So we look at predecessors up to max_hops
                rev_g = g.reverse(copy=False)
                for target, length in nx.single_source_shortest_path_length(
                    rev_g, node, cutoff=max_hops
                ).items():
                    if length > 0:
                        in_bm.add(self.uuid_to_int[target])
                self.inbound_bitmaps[u_idx] = in_bm

                # Undirected
                un_bm = pyroaring.BitMap()
                for target, length in nx.single_source_shortest_path_length(
                    undir_g, node, cutoff=max_hops
                ).items():
                    if length > 0:
                        un_bm.add(self.uuid_to_int[target])
                self.undirected_bitmaps[u_idx] = un_bm

    def get_shortest_path(self, source: UUID, target: UUID) -> tuple[int, str, list[UUID]] | None:
        if source == target:
            return (0, "self", [source])

        if source not in self.uuid_to_int or target not in self.uuid_to_int:
            return None

        s_idx = self.uuid_to_int[source]
        t_idx = self.uuid_to_int[target]

        # We need the hop count and path, but bitmaps only tell us reachability.
        # To get the exact path/hops, we must still traverse if it's reachable!
        # This is why bitmaps don't make sense for returning detailed paths at our scale.

        if t_idx in self.outbound_bitmaps.get(s_idx, pyroaring.BitMap()):
            # Reachable outbound, fallback to NetworkX to get exact shortest path
            return NetworkXReachability(self.graph).get_shortest_path(source, target)

        if t_idx in self.inbound_bitmaps.get(s_idx, pyroaring.BitMap()):
            return NetworkXReachability(self.graph).get_shortest_path(source, target)

        if t_idx in self.undirected_bitmaps.get(s_idx, pyroaring.BitMap()):
            return NetworkXReachability(self.graph).get_shortest_path(source, target)

        return None


# The active implementation is NetworkX.
# Reason: At 5 edges (and even at much larger sizes for simple paths),
# the overhead of maintaining and intersecting compressed bitmaps
# is slower than direct NetworkX traversal, especially since we need
# the actual path and hop counts for evidence and decaying score.
# Shipping an unused Bitmap implementation is just to prove the interface.

reachability: Reachability = NetworkXReachability(graph_instance)

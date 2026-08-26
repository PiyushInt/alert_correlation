import random
import uuid
from unittest.mock import patch

import networkx as nx

from ace.dependency.graph import DependencyGraph
from ace.dependency.reachability import BitmapReachability, NetworkXReachability


def _generate_random_graph(node_count: int, edge_count: int) -> DependencyGraph:
    nodes = [uuid.uuid4() for _ in range(node_count)]
    g = nx.DiGraph()
    g.add_nodes_from(nodes)

    edges_added = 0
    while edges_added < edge_count:
        u = random.choice(nodes)
        v = random.choice(nodes)
        if u != v and not g.has_edge(u, v):
            g.add_edge(u, v, source="inventory")
            edges_added += 1

    dg = DependencyGraph()
    dg._graph = g
    return dg


def test_reachability_equivalence():
    # 100 queries on a ~5 edge graph
    dg = _generate_random_graph(10, 5)
    nx_reach = NetworkXReachability(dg)
    bm_reach = BitmapReachability(dg)

    nodes = list(dg._graph.nodes)

    with patch("ace.config.settings.MAX_INCIDENT_HOPS", 3):
        # We must re-init bm_reach because MAX_INCIDENT_HOPS changed
        bm_reach = BitmapReachability(dg)

        matches = 0
        for _ in range(100):
            u = random.choice(nodes)
            v = random.choice(nodes)

            res_nx = nx_reach.get_shortest_path(u, v)
            res_bm = bm_reach.get_shortest_path(u, v)

            if res_nx is None:
                assert res_bm is None
            else:
                assert res_bm is not None
                assert res_nx[0] == res_bm[0]
                assert res_nx[1] == res_bm[1]
                assert res_nx[2] == res_bm[2]

            matches += 1

        assert matches == 100

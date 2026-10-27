"""
Bipartite circuit graphs and topology comparison, in one place.

Topology novelty asks whether a generated circuit is isomorphic to any circuit in
the dataset. Answering that means turning both sides into the same kind of graph -
a generated walk from its token stream, a dataset circuit from its adjacency
matrix - and comparing them under the same notion of "the same". The metrics that
report novelty share this module so that they cannot drift apart on either half.

Device generalisation
    `NM1` and `NM7` are the same kind of node, so device numbers are stripped
    before comparison (`generalize_token`). External ports and power rails keep
    their identity - `VIN1` and `VOUT1` are different terminals, not two instances
    of one device - and so do edge tokens and the circuit type token.

Matching
    Nodes match on their generalised token type, edges on their typed pin label,
    so two circuits are isomorphic only when the wiring *and* the pin roles agree.

Only `CORE_Vocab` is imported from the package, for the token index maps and the
edge-token set. Nothing in the generation path imports this module: it pulls in
networkx and pandas, which the decoder has no use for.
"""

import os
import re

import networkx as nx
import pandas as pd
from tqdm import tqdm

from CORE_Vocab import stoi, itos, all_edge_types

ALL_EDGES = set(all_edge_types)


# ============================================================================
# Walk -> graph
# ============================================================================
def sequence_to_graph(seq):
    """Convert a circuit sequence to a bipartite graph representation.

    Returns:
        node_indices: List of unique node token indices (not edge types)
        edges: List of (src_idx, dst_idx, edge_type) tuples
    """
    seq_indices = [stoi.get(str(token), stoi.get('VSS', 0)) for token in seq]

    first_token_str = str(seq[0])
    start_idx = 1 if first_token_str.startswith('CIRCUIT_') else 0

    end_tokens = ('TRUNCATE', 'End')
    edge_types = ALL_EDGES

    # Extract nodes (skip edge types)
    nodes_set = set()
    seq_len = len(seq)

    for i in range(start_idx, seq_len):
        token_str = str(seq[i])
        if token_str in end_tokens:
            break
        if token_str not in edge_types:
            token_idx = seq_indices[i]
            nodes_set.add(token_idx)

    node_indices = sorted(list(nodes_set))
    node_to_graph_idx = {token_idx: graph_idx for graph_idx, token_idx in enumerate(node_indices)}

    # Build edges with types (format: node -> edge_type -> node)
    edges = []
    i = start_idx
    while i < seq_len - 1:
        token_str = str(seq[i])
        if token_str in end_tokens:
            break

        # Pattern: node -> edge_type -> node
        if token_str not in edge_types:
            node1_idx = seq_indices[i]

            # Look for edge_type -> node2
            if i + 2 < seq_len:
                edge_type_str = str(seq[i + 1])
                node2_str = str(seq[i + 2])

                if edge_type_str in edge_types and node2_str not in edge_types:
                    node2_idx = seq_indices[i + 2]

                    if node1_idx in node_to_graph_idx and node2_idx in node_to_graph_idx:
                        graph_idx1 = node_to_graph_idx[node1_idx]
                        graph_idx2 = node_to_graph_idx[node2_idx]

                        # Add undirected edges
                        edges.append((graph_idx1, graph_idx2, edge_type_str))
                        edges.append((graph_idx2, graph_idx1, edge_type_str))

        i += 1

    return node_indices, edges


def generalize_token(token_str):
    """Generalize token by removing device numbers (NM1 -> NM).

    External ports, power rails, edge tokens and the circuit type token keep their
    identity: they name a specific terminal or connection, not one instance of a
    device family.
    """
    special_tokens = {'VDD', 'VSS', 'TRUNCATE', 'End', 'VOUT'}

    # External ports (preserve identity)
    for i in range(1, 21):
        special_tokens.add(f"VIN{i}")
    for i in range(1, 8):
        special_tokens.add(f"VOUT{i}")
    for i in range(1, 4):
        special_tokens.add(f"IIN{i}")
    for i in range(1, 6):
        special_tokens.add(f"IOUT{i}")
    for i in range(1, 12):
        special_tokens.add(f"VB{i}")
    for i in range(1, 8):
        special_tokens.add(f"IB{i}")
    for i in range(1, 22):
        special_tokens.add(f"VCONT{i}")
    for i in range(1, 4):
        special_tokens.update([f"VCM{i}", f"VREF{i}", f"IREF{i}", f"VRF{i}", f"VIF{i}"])
    for i in range(1, 6):
        special_tokens.update([f"VLO{i}", f"VBB{i}"])

    # Edge types (preserve)
    if token_str in special_tokens or token_str in ALL_EDGES:
        return token_str

    if token_str.startswith('CIRCUIT_'):
        return token_str

    # Remove numbers: NM1->NM, NET1->NET
    generalized = re.sub(r'(\D+)\d+', r'\1', token_str)
    return generalized


def create_networkx_graph(seq, generalize_devices=True):
    """Create a NetworkX graph from a sequence (bipartite, with typed edges)."""
    node_indices, edges = sequence_to_graph(seq)

    G = nx.Graph()

    # Add nodes with token type
    for graph_idx, token_idx in enumerate(node_indices):
        token_str = itos.get(token_idx, 'UNKNOWN')
        if generalize_devices:
            token_type = generalize_token(token_str)
        else:
            token_type = token_str
        G.add_node(graph_idx, token_type=token_type)

    # Add edges with edge type as attribute
    for src, dst, edge_type in edges:
        if src != dst:
            if generalize_devices:
                edge_type_gen = generalize_token(edge_type)
            else:
                edge_type_gen = edge_type
            G.add_edge(src, dst, edge_type=edge_type_gen)

    return G


def graphs_are_isomorphic(G1, G2):
    """Whether two circuits are isomorphic, matching node types and edge types."""
    if G1.number_of_nodes() != G2.number_of_nodes():
        return False
    if G1.number_of_edges() != G2.number_of_edges():
        return False

    def node_match(n1, n2):
        """Nodes match when their (device-generalised) token types agree."""
        return n1.get('token_type') == n2.get('token_type')

    def edge_match(e1, e2):
        """Edges match when their edge types agree."""
        return e1.get('edge_type') == e2.get('edge_type')

    return nx.is_isomorphic(G1, G2, node_match=node_match, edge_match=edge_match)


# ============================================================================
# Dataset -> graph
# ============================================================================
def load_csv_bipartite_graph(csv_path, generalize_devices=True):
    """Load bipartite graph from a CSV adjacency matrix with typed edges."""
    df = pd.read_csv(csv_path, index_col=0)

    G = nx.Graph()
    nodes = list(df.index)

    # Add nodes
    for idx, node_name in enumerate(nodes):
        if generalize_devices:
            token_type = generalize_token(str(node_name))
        else:
            token_type = str(node_name)
        G.add_node(idx, token_type=token_type)

    # Add edges with types
    for i, node1 in enumerate(nodes):
        for j, node2 in enumerate(nodes):
            if i < j:
                edge_type = df.iloc[i, j]
                if edge_type != '0' and edge_type != 0 and pd.notna(edge_type):
                    edge_type_str = str(edge_type)
                    if generalize_devices:
                        edge_type_gen = generalize_token(edge_type_str)
                    else:
                        edge_type_gen = edge_type_str
                    G.add_edge(i, j, edge_type=edge_type_gen)

    return G


def circuit_ids(dataset_dir):
    """Numbered circuit folders present under dataset_dir, in numeric order.

    The ids are sparse, so the folders are listed rather than a fixed range
    being scanned: the count follows whatever the directory actually holds.
    """
    if not os.path.isdir(dataset_dir):
        return []
    return sorted((entry.name for entry in os.scandir(dataset_dir)
                   if entry.is_dir() and entry.name.isdigit()), key=int)


def load_dataset_graphs(dataset_path='Dataset', max_graphs=None, with_ids=False):
    """Load every Graph_Bipart<id>.csv under dataset_path as a generalised graph.

    Args:
        dataset_path: root directory holding the numbered circuit folders
        max_graphs: stop after this many graphs (None: load all)
        with_ids: return (circuit_id, graph) pairs instead of graphs
    """
    print(f"\nLoading dataset graphs from {dataset_path}...")

    graphs = []
    for folder_num in tqdm(circuit_ids(dataset_path), desc="Loading dataset"):
        csv_path = os.path.join(dataset_path, folder_num, f"Graph_Bipart{folder_num}.csv")

        if not os.path.exists(csv_path):
            continue

        try:
            G = load_csv_bipartite_graph(csv_path, generalize_devices=True)
            if G.number_of_nodes() > 0:
                graphs.append((int(folder_num), G) if with_ids else G)
        except Exception:
            continue

        if max_graphs and len(graphs) >= max_graphs:
            break

    print(f"Loaded {len(graphs)} dataset graphs\n")
    return graphs

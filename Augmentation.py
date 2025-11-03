import pandas as pd
import numpy as np
import os
import sys
# Check current recursion limit
print("Current recursion limit:", sys.getrecursionlimit())

# Increase recursion limit
new_limit = 9000  # Set to a higher value
sys.setrecursionlimit(new_limit)

print("New recursion limit:", sys.getrecursionlimit())

def read_connection_matrix(filename):
    """
    Reads the connection matrix from a CSV file and returns it as a DataFrame.
    """
    return pd.read_csv(filename, index_col=0)

def get_edges_from_path(traversal_path):
    """Extracts the directed edges from a given traversal path."""
    return [(traversal_path[i], traversal_path[i + 1]) for i in range(len(traversal_path) - 1)]

def check_if_path_covers_all_edges_exactly_once(matrix, traversal_path):
    """Checks if the given traversal path covers all directed edges in the connection matrix exactly once."""
    # Extract all edges from the traversal path
    path_edges = get_edges_from_path(traversal_path)

    # Extract all edges from the connection matrix
    graph_edges = set()
    for i in matrix.index:
        for j in matrix.columns:
            if matrix.loc[i, j] == 1:
                graph_edges.add((i, j))

    # Check if all graph edges are covered by path edges exactly once
    if len(path_edges) != len(graph_edges):
        return False

    path_edges_count = {edge: path_edges.count(edge) for edge in path_edges}
    if any(count > 1 for count in path_edges_count.values()):
        return False

    return set(path_edges) == graph_edges
  
def dfs_traversal(matrix, start_node='VSS'):
    """
    Performs a DFS traversal on the connection matrix starting from the specified node 
    and returns the traversal path as an array of nodes.
    """
    visited_edges = set()
    traversal_path = []

    def dfs(node):
        traversal_path.append(node)
        for neighbor in matrix.columns:
            if matrix.at[node, neighbor] == 1 and (node, neighbor) not in visited_edges:
                visited_edges.add((node, neighbor))
                visited_edges.add((neighbor, node))  # Since the graph is undirected
                dfs(neighbor)
                traversal_path.append(node)  # Record the path back
    
    # Start DFS from the specified start node
    if start_node in matrix.index:
        dfs(start_node)
    
    # Generate a set of all edges in the graph
    all_edges = set()
    for node in matrix.index:
        for neighbor in matrix.columns:
            if matrix.at[node, neighbor] == 1:
                all_edges.add((node, neighbor))
                all_edges.add((neighbor, node))  # Since the graph is undirected
    
    return traversal_path, check_if_path_covers_all_edges_exactly_once(matrix, traversal_path)

def dfs_traversal_after(matrix, start_node='VSS', visited_edges = {}, traversal_path = []):
    """
    Performs a DFS traversal on the connection matrix starting from the specified node 
    and returns the traversal path as an array of nodes.
    """
    def dfs(node):
        traversal_path.append(node)
        for neighbor in matrix.columns:
            if matrix.at[node, neighbor] == 1 and (node, neighbor) not in visited_edges:
                visited_edges.add((node, neighbor))
                visited_edges.add((neighbor, node))  # Since the graph is undirected
                dfs(neighbor)
                traversal_path.append(node)  # Record the path back
    
    # Start DFS from the specified start node
    if start_node in matrix.index:
        dfs(start_node)

    return traversal_path

def dfs_all_continue(matrix, all_paths, unique_paths, max_solutions=2000):

    if len(all_paths)>max_solutions-1:
        stop = True
    else:
        stop = False
    for path_first in (all_paths):
        if stop == True:
            break
        visited_edges = set()
        for i in range(len(path_first)-1):
            if stop == True:
                break
            visited_edges.add((path_first[i], path_first[i+1]))
            visited_edges.add((path_first[i+1], path_first[i]))
            for neighbor in matrix.columns:
                if matrix.at[path_first[i], neighbor] == 1 and (path_first[i], neighbor) not in visited_edges:
                    visited_edges.add((path_first[i], neighbor))
                    visited_edges.add((neighbor, path_first[i]))
                    new_visited_edges = set()
                    if i!=0:
                        for z in range (i):
                            new_visited_edges.add((path_first[z], path_first[z+1]))
                            new_visited_edges.add((path_first[z+1], path_first[z]))
                    new_visited_edges.add((path_first[i], neighbor))
                    new_visited_edges.add((neighbor, path_first[i]))

                    newpath = []
                    for z in range (i+1):
                        newpath.append(path_first[z])
                    newnewpath = newpath.copy()
                    path = dfs_traversal_after(matrix,neighbor,new_visited_edges,newpath)
                    path.extend(newnewpath[::-1])
                    path_tuple = tuple(path)
                    if check_if_path_covers_all_edges_exactly_once(matrix, path):
                        if path_tuple not in unique_paths:
                            unique_paths.add(path_tuple)
                            all_paths.append(path.copy())
                if len(all_paths)>max_solutions-1:
                    stop = True
                    break
    return all_paths, unique_paths

def dfs_all_paths(matrix, start_node='VSS', max_solutions=2000, run_num = 10):
    """
    Performs a DFS traversal on the connection matrix starting from the specified node 
    and returns up to max_solutions complete traversal paths as a list of arrays of nodes.
    """

    all_paths = []
    unique_paths = set()

    path_first, result = dfs_traversal(matrix, start_node)

    if result == False:
        print('error')
        return None
    path_tuple = tuple(path_first)
    if path_tuple not in unique_paths:
        unique_paths.add(path_tuple)
        all_paths.append(path_first.copy())

    for run in range (run_num):
        all_paths, unique_paths = dfs_all_continue(matrix,all_paths,unique_paths,max_solutions)

    return all_paths


def get_circuit_category(dataset_number):
    """
    데이터셋 번호에 따른 회로 카테고리를 반환합니다.
    data_categorization.md를 기반으로 분류합니다.
    """
    if 281 <= dataset_number <= 336 or 1781 <= dataset_number <= 2180:
        return "CIRCUIT_Opamp"
    elif 632 <= dataset_number <= 635 or 1045 <= dataset_number <= 1080:
        return "CIRCUIT_Comparator"
    elif (403 <= dataset_number <= 437) or (521 <= dataset_number <= 544) or (640 <= dataset_number <= 646) or (1109 <= dataset_number <= 1190):
        return "CIRCUIT_Oscillator"
    elif 98 <= dataset_number <= 159 or 604 <= dataset_number <= 613 or 834 <= dataset_number <= 867:
        return "CIRCUIT_Current_Mirror"
    elif 69 <= dataset_number <= 97 or 614 <= dataset_number <= 621:
        return "CIRCUIT_Differential_Amp"
    elif (461 <= dataset_number <= 492) or (1081 <= dataset_number <= 1090):
        return "CIRCUIT_LNA"
    elif (494 <= dataset_number <= 520) or (1091 <= dataset_number <= 1099):
        return "CIRCUIT_Mixer"
    elif 2181 <= dataset_number <= 2630:
        return "CIRCUIT_LDO"
    elif (368 <= dataset_number <= 384) or (624 <= dataset_number <= 627) or (1461 <= dataset_number <= 1780):
        return "CIRCUIT_Bandgap_Ref"
    elif 1 <= dataset_number <= 68 or 822 <= dataset_number <= 833 or 669 <= dataset_number <= 687:
        return "CIRCUIT_Single_Stage_Amp"
    elif 578 <= dataset_number <= 592 or 1100 <= dataset_number <= 1108:
        return "CIRCUIT_Power_Amp"
    elif 726 <= dataset_number <= 737:
        return "CIRCUIT_Voltage_Regulator"
    elif 768 <= dataset_number <= 788 or 651 <= dataset_number <= 651:
        return "CIRCUIT_Filter"
    elif 2631 <= dataset_number <= 3502:
        return "CIRCUIT_Switched_Cap"
    else:
        return "CIRCUIT_General"


# Dictionary of directories and their respective end values
base_dirs = {
    "Dataset": 3502
}

# Loop through each base directory
for base_dir, end in base_dirs.items():
    for i in range(1, end+1):  # Iterate through numbered subdirectories
        max_solutions = 20 if i > 1280 else 200  # Set max_solutions based on directory
        number = str(i)
        dir_path = f"{base_dir}/{number}"
        if not os.path.isdir(dir_path):
            # If it doesn't exist, skip the rest of this loop iteration
            # print(f"Directory '{dir_path}' does not exist. Skipping...")
            continue
        
        connect_dir = os.path.join(base_dir, number, f'Graph{number}.csv')

        # Check if the connection matrix file exists
        if not os.path.exists(connect_dir):
            print(f"Connection matrix file not found: {connect_dir}")
            continue

        try:
            # Read the connection matrix
            connection_matrix = read_connection_matrix(connect_dir)

            # Perform DFS traversal starting from VSS
            all_traversal_paths = dfs_all_paths(connection_matrix, start_node='VSS', max_solutions=max_solutions)

            # Check if all paths cover all edges exactly once
            if not all(check_if_path_covers_all_edges_exactly_once(connection_matrix, path) for path in all_traversal_paths):
                print(f"DATA {base_dir}/{number}: Paths do not cover edges exactly once")
                break

            # Get circuit category for this dataset
            circuit_type = get_circuit_category(int(number))
            
            # Add circuit type to the beginning of each path and pad to length 1025
            padded_paths = []
            for path in all_traversal_paths:
                if len(path) <= 1024:  # 1024 because we'll add 1 circuit type token
                    # Add circuit type at the beginning
                    labeled_path = [circuit_type] + path
                    # Pad to total length of 1025
                    padded_path = labeled_path + ['TRUNCATE'] * (1025 - len(labeled_path))
                    padded_paths.append(padded_path)

            # Output the number of complete paths with circuit type info
            print(f"DATA {base_dir}/{number} ({circuit_type}): Number of complete paths: {len(padded_paths)}")

            # Check if all paths are unique
            if len(padded_paths) != len(set(tuple(path) for path in padded_paths)):
                print(f"DATA {base_dir}/{number}: Paths are not unique")
                break

            # Save the padded paths to a file
            save_dir = os.path.join(base_dir, number, f'Sequence_total{number}.npy')
            np.save(save_dir, padded_paths)

        except Exception as e:
            print(f"Error processing {base_dir}/{number}: {e}")
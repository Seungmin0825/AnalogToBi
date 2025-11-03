import os
import re
from collections import defaultdict

def count_files_with_types(directory, types):
    """Count files containing specific device types in the directory."""
    type_counts = defaultdict(int)  # Dictionary to store counts for each type

    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r') as file:
                content = file.read().strip()
                
                # Parse tokens by splitting on '->'
                tokens = [token.strip() for token in content.split('->') if token.strip()]
                
                # Skip first token if it's a CIRCUIT_* style token
                if tokens and tokens[0].startswith('CIRCUIT_'):
                    tokens = tokens[1:]
                
                # Extract device types from tokens
                found_types = set()
                for token in tokens:
                    # Check for exact device type matches
                    for device_type in types:
                        if device_type == "TRANSMISSION_GATE":
                            # Special handling for TRANSMISSION_GATE
                            # Match patterns like TRANSMISSION_GATE5, TRANSMISSION_GATE3_A, etc.
                            if re.match(r'^TRANSMISSION_GATE\d+', token):
                                found_types.add(device_type)
                                break
                        else:
                            # Standard pattern: letters followed by digits (e.g., NM1, L5, PM3)
                            match = re.match(r'^' + re.escape(device_type) + r'\d+', token)
                            if match:
                                found_types.add(device_type)
                                break
                
                # Count this file for each device type found
                for device_type in found_types:
                    type_counts[device_type] += 1

    return type_counts

# Define the directory and types to search for
# Use INFERENCE_DIR env var if provided, otherwise default to local 'Inference' folder
directory = os.environ.get('INFERENCE_DIR', 'Inference')
types = ["NM", "PM", "NPN", "PNP", "R", "C", "L", "DIO", "XOR", "PFD", "INVERTER", "TRANSMISSION_GATE"]

# Count files containing each type
type_counts = count_files_with_types(directory, types)

# Define the desired output order
output_order = ["NM", "PM", "R", "C", "L", "NPN", "DIO", "PNP", "INVERTER", "TRANSMISSION_GATE", "XOR"]

# Print the results in the specified order
print("File counts for each type:")
for device_type in output_order:
    if device_type in type_counts:
        print(f"{device_type}: {type_counts[device_type]}")

# Total files containing any of the types
total_files = sum(type_counts.values())
print(f"\nTotal files containing any of the specified types: {total_files}")
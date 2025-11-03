import os
import importlib.util

def run_simulation(file_path):
    """Dynamically import and execute a PySpice simulation file."""
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

def check_for_unsupported_pins_or_device(file_path):
    """Check if the file contains unsupported pin type errors."""
    with open(file_path, 'r') as f:
        content = f.read()
    return "# Unsupported" in content

def main():
    spice_dir = "SPICE"
    if not os.path.exists(spice_dir):
        print(f"Directory '{spice_dir}' does not exist.")
        return

    valid_count = 0
    invalid_unsupported = 0  # Count for unsupported device or pin
    invalid_execution_fail = 0  # Count for execution failures

    # Iterate over all generated PySpice files
    for file_name in os.listdir(spice_dir):
        if file_name.startswith("run") and file_name.endswith(".py"):
            file_path = os.path.join(spice_dir, file_name)
            print(f"\nProcessing {file_path}...")

            # Check for unsupported pin types
            if check_for_unsupported_pins_or_device(file_path):
                print(f"Invalid circuit: Unsupported external pin type found in {file_name}")
                invalid_unsupported += 1
                continue

            # Try running the simulation
            try:
                run_simulation(file_path)
                print(f"Valid circuit: {file_name} executed successfully.")
                valid_count += 1
            except Exception as e:
                print(f"Invalid circuit: Error while running {file_name}: {e}")
                invalid_execution_fail += 1

    # Print summary
    print("\nSimulation Summary:")
    print(f"Valid circuits: {valid_count}")
    print(f"Invalid circuits (unsupported device or pin): {invalid_unsupported}")
    print(f"Invalid circuits (execution failure): {invalid_execution_fail}")

if __name__ == "__main__":
    main()
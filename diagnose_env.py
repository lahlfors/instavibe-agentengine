import sys
import os
import importlib.util

print("--- Python Environment Diagnostic ---")
print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print("\n--- sys.path ---")
for path in sys.path:
    print(path)
print("\n------------------")

print("\n--- Checking for 'google.auth.transport.aiohttp' ---")
try:
    import google.auth.transport.aiohttp
    print("SUCCESS: Successfully imported 'google.auth.transport.aiohttp'.")

    # Find the location of the google.auth package
    spec = importlib.util.find_spec("google.auth")
    if spec and spec.submodule_search_locations:
        print(f"Location of 'google.auth' package: {spec.submodule_search_locations[0]}")
    else:
        print("Could not determine the location of the 'google.auth' package.")

except ModuleNotFoundError as e:
    print(f"ERROR: Failed to import 'google.auth.transport.aiohttp'.")
    print(f"Exact error: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

print("\n--- Diagnostic Complete ---")

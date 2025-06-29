#!/usr/bin/env python
import sys
import os
import site

print("--- Attempting to import OpenTelemetry GCP Propagator ---")
sys.stdout.flush()
try:
    import opentelemetry.propagators.gcp
    print("Successfully imported opentelemetry.propagators.gcp")
    print("Location: {}".format(opentelemetry.propagators.gcp.__file__))
    from opentelemetry.propagators.gcp import GcpCloudTraceFormatPropagator
    print("Successfully imported GcpCloudTraceFormatPropagator from opentelemetry.propagators.gcp")
    sys.stdout.flush()
    sys.exit(0) # Explicitly exit with 0 on success
except ImportError as e_import:
    print("!!! FAILED to import OpenTelemetry GCP Propagator (ImportError): {}".format(e_import))
except Exception as e_general:
    print("!!! FAILED to import OpenTelemetry GCP Propagator (Other Exception): {}".format(e_general))

# This part is reached only if an exception occurred
print("--- Diagnostics for OpenTelemetry Failure ---")
sys.stderr.flush() # Ensure error messages are flushed
sys.stdout.flush() # Ensure info messages are flushed

print("Python sys.path:")
for p in sys.path: print(p)
sys.stdout.flush()

print("Site packages:")
site_pkgs = []
try:
    site_pkgs = site.getsitepackages()
    print(site_pkgs)
    if site_pkgs and len(site_pkgs) > 0 and os.path.exists(site_pkgs[0]):
        print("Contents of first site-package dir ({}):".format(site_pkgs[0]))
        try:
            print(os.listdir(site_pkgs[0]))
        except Exception as e_listdir:
            print("Error listing site-packages: {}".format(e_listdir))
    else:
        print("No site-packages found or first one invalid.")
except Exception as e_site:
    print("Error getting site packages: {}".format(e_site))
sys.stdout.flush()
sys.stderr.flush()
sys.exit(1)

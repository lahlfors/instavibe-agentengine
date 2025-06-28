#!/usr/bin/env python
import sys
import os
import site

print('--- Python sys.path during build: ---')
for p in sys.path:
    print(p)
sys.stdout.flush()

print('--- Attempting to import a2a_common and submodules ---')
try:
    import a2a_common
    print('Successfully imported a2a_common, location: ' + str(a2a_common.__file__))
    sys.stdout.flush()

    import a2a_common.utils.logging_setup
    print('Successfully imported a2a_common.utils.logging_setup, location: ' + str(a2a_common.utils.logging_setup.__file__))
    sys.stdout.flush()

    print('--- a2a_common import verification successful ---')
    sys.stdout.flush()
    sys.exit(0) # Explicitly exit with 0 on success

except ImportError as e_import:
    print('!!! Python import verification FAILED (ImportError): {}'.format(e_import))
    sys.stderr.flush()
except Exception as e_general:
    print('!!! Python import verification FAILED (General Exception): {}'.format(e_general))
    sys.stderr.flush()

# This part is reached only if an exception occurred in the try block (and sys.exit(0) was not called)
print('--- Diagnostics on failure ---')
print('Python sys.path on failure (re-printing):')
for p_fail in sys.path: print(p_fail)
sys.stdout.flush()

print('Site packages:')
site_pkgs = []
try:
    site_pkgs = site.getsitepackages()
    print(site_pkgs)
    if site_pkgs and len(site_pkgs) > 0 and os.path.exists(site_pkgs[0]):
        print('Contents of first site-package dir ({}):'.format(site_pkgs[0]))
        try:
            print(os.listdir(site_pkgs[0]))
        except Exception as e_listdir:
            print('Error listing site-packages contents: {}'.format(e_listdir))
    else:
        print('No site-packages found by site.getsitepackages() or first one is invalid/inaccessible')
except Exception as e_site:
    print('Error getting site packages: {}'.format(e_site))
sys.stdout.flush()
sys.stderr.flush()
sys.exit(1) # Exit with 1 if we reached here (meaning an exception occurred)

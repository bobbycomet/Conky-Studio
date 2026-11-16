from __future__ import annotations

import sys

# Support/diagnostic flags: answered without Qt, so they also work on a minimal system
# with no display or graphics libraries.
if any(a in ("--version", "--deps-report") for a in sys.argv[1:]):
    if "--version" in sys.argv[1:]:
        from conkystudio import __version__
        print(f"Conky Studio {__version__}")
    else:
        from conkystudio.hardware import deps
        print(deps.report_json())
    sys.exit(0)

from conkystudio.app import main

if __name__ == "__main__":
    sys.exit(main())

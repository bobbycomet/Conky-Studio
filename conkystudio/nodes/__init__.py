"""
Importing this package populates the node registry as a side effect --
every submodule below calls registry.register(...) at import time. Any
code that needs to look up node types (the UI palette, the codegen
dispatcher, tests) should `import conkystudio.nodes` first to guarantee
the registry is populated, then use conkystudio.nodes.registry.get/all_specs.
"""
from conkystudio.nodes import registry  # noqa: F401
from conkystudio.nodes import canvas  # noqa: F401  (registers canvas.root)
from conkystudio.nodes import sources_native  # noqa: F401
from conkystudio.nodes import sources_external  # noqa: F401
from conkystudio.nodes import logic  # noqa: F401
from conkystudio.nodes import visuals  # noqa: F401
from conkystudio.nodes import visuals_niche 
import conkystudio.extensions_bootstrap  # noqa: F401
from . import logic_extra       # noqa: F401
from . import sources_extra     # noqa: F401
from . import visuals_extra     # noqa: F401
from . import visuals_more      # noqa: F401
import conkystudio.extensions_bootstrap  # noqa: F401
__all__ = ["registry"]

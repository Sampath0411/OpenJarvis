"""Automations package — importing it registers all built-in tools."""
from .registry import REGISTRY, tool  # noqa: F401

# import side-effect modules so their @tool decorators run
from . import system as _system            # noqa: F401,E402
from . import web as _web                  # noqa: F401,E402
from . import files as _files              # noqa: F401,E402
from . import utils as _utils              # noqa: F401,E402
from . import media as _media              # noqa: F401,E402
from . import launcher as _launcher        # noqa: F401,E402
from . import memory_tools as _memory_tools  # noqa: F401,E402
from . import rag as _rag                  # noqa: F401,E402
from . import messaging as _messaging      # noqa: F401,E402
from . import notify_tools as _notify_tools  # noqa: F401,E402
from . import vision_tools as _vision_tools  # noqa: F401,E402
from . import owner_tools as _owner_tools    # noqa: F401,E402
from . import creator as _creator            # noqa: F401,E402
from . import email_tool as _email_tool      # noqa: F401,E402
from . import code_tools as _code_tools      # noqa: F401,E402
from . import phone_tools as _phone_tools    # noqa: F401,E402

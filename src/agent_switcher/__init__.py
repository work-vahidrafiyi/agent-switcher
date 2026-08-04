"""Provider-neutral CLI account switcher."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("agent-switcher")
except PackageNotFoundError:
    __version__ = "0+unknown"

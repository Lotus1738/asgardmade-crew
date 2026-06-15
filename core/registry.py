"""
core/registry.py
================
Central registry for all BusinessModule subclasses.

On import, auto-discovers every module package under modules/ and registers
any class that subclasses BusinessModule. New business types are added by
dropping a new directory under modules/ with a module.py — no changes
to this file needed.

Usage:
    from core.registry import registry

    # List all registered modules
    registry.list()                        # [{"module_id": ..., "name": ...}, ...]

    # Get a specific module instance
    m = registry.get("etsy_printify")      # EtsyPrintifyModule instance

    # Check if a module is registered
    registry.has("kdp")                    # True / False
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Type

from core.business_module import BusinessModule


class ModuleRegistry:
    """Auto-discovering registry of BusinessModule implementations."""

    def __init__(self) -> None:
        # module_id -> instance
        self._modules: Dict[str, BusinessModule] = {}
        self._discovered = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """
        Walk the modules/ package and import every module.py inside it.
        Any BusinessModule subclass found gets registered automatically.
        Safe to call multiple times — skips if already discovered.
        """
        if self._discovered:
            return
        self._discovered = True

        try:
            import modules as _pkg
        except ImportError:
            print("[REGISTRY] 'modules' package not found — no auto-discovery")
            return

        for _finder, name, _is_pkg in pkgutil.walk_packages(
            path=_pkg.__path__,
            prefix=_pkg.__name__ + ".",
            onerror=lambda n: print(f"[REGISTRY] Error walking {n}"),
        ):
            # Only import leaf module.py files, e.g. modules.etsy_printify.module
            if not name.endswith(".module"):
                continue
            try:
                importlib.import_module(name)
            except Exception as e:
                print(f"[REGISTRY] Failed to import {name}: {e}")

    def _auto_register_subclasses(self) -> None:
        """Register any BusinessModule subclass that defined MODULE_ID."""
        for cls in _all_subclasses(BusinessModule):
            mid = getattr(cls, "MODULE_ID", "")
            if mid and mid != "base" and mid not in self._modules:
                try:
                    instance = cls()
                    self._modules[mid] = instance
                    print(f"[REGISTRY] Registered: {cls.__name__} ({mid})")
                except Exception as e:
                    print(f"[REGISTRY] Could not instantiate {cls.__name__}: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, module: BusinessModule) -> None:
        """Manually register a module instance (useful for testing)."""
        self._modules[module.MODULE_ID] = module
        print(f"[REGISTRY] Manually registered: {module.MODULE_ID}")

    def get(self, module_id: str) -> BusinessModule | None:
        """Return the module instance for module_id, or None."""
        self._ensure_loaded()
        return self._modules.get(module_id)

    def get_or_default(self, module_id: str | None = None) -> BusinessModule:
        """
        Return requested module, falling back to etsy_printify, then the
        first registered module. Raises if registry is completely empty.
        """
        self._ensure_loaded()
        if module_id and module_id in self._modules:
            return self._modules[module_id]
        if "etsy_printify" in self._modules:
            return self._modules["etsy_printify"]
        if self._modules:
            return next(iter(self._modules.values()))
        raise RuntimeError("No business modules registered")

    def has(self, module_id: str) -> bool:
        self._ensure_loaded()
        return module_id in self._modules

    def list(self) -> list[dict]:
        """Return metadata dicts for all registered modules, sorted by name."""
        self._ensure_loaded()
        return sorted(
            [m.meta() for m in self._modules.values()],
            key=lambda x: x["name"],
        )

    def ids(self) -> list[str]:
        self._ensure_loaded()
        return list(self._modules.keys())

    def _ensure_loaded(self) -> None:
        if not self._discovered:
            self.discover()
            self._auto_register_subclasses()
        elif not self._modules:
            self._auto_register_subclasses()

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._modules)

    def __repr__(self) -> str:
        return f"<ModuleRegistry modules={self.ids()}>"


def _all_subclasses(cls: type) -> list[type]:
    """Recursively collect all subclasses of cls."""
    result = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_subclasses(sub))
    return result


# Singleton — import this everywhere
registry = ModuleRegistry()

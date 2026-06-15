"""
Skill Pack registry for AsgardMade Pantheon.

A skill is an async callable with this signature:
  async def run(args: dict) -> SkillResult

Skills are registered with metadata: name, description, pack, args schema.
The OS dashboard can list, invoke, and chain skills.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
from datetime import datetime

SkillFn = Callable[[dict], Coroutine[Any, Any, "SkillResult"]]


@dataclass
class SkillResult:
    success: bool
    output: Any          # main result (str, list, dict)
    summary: str = ""    # one-line human-readable summary
    error: str = ""
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "summary": self.summary,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class SkillMeta:
    name: str
    description: str
    pack: str               # "research", "content", "google", "custom"
    fn: SkillFn
    args_schema: dict = field(default_factory=dict)   # {arg_name: description}
    tags: list[str] = field(default_factory=list)
    icon: str = "⚡"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "pack": self.pack,
            "args_schema": self.args_schema,
            "tags": self.tags,
            "icon": self.icon,
        }


# ─── Global registry ─────────────────────────────────────────────────────────

_REGISTRY: dict[str, SkillMeta] = {}
_RUN_LOG: list[dict] = []


def register(meta: SkillMeta) -> None:
    _REGISTRY[meta.name] = meta


def list_skills(pack: str | None = None) -> list[dict]:
    skills = list(_REGISTRY.values())
    if pack:
        skills = [s for s in skills if s.pack == pack]
    return [s.to_dict() for s in skills]


def list_packs() -> list[str]:
    return sorted(set(s.pack for s in _REGISTRY.values()))


async def run_skill(name: str, args: dict | None = None) -> SkillResult:
    """Run a skill by name. Returns SkillResult."""
    args = args or {}
    if name not in _REGISTRY:
        return SkillResult(success=False, output=None, error=f"Skill '{name}' not found")
    meta = _REGISTRY[name]
    t0 = datetime.now()
    try:
        result = await meta.fn(args)
        result.duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _RUN_LOG.append({
            "skill": name,
            "pack": meta.pack,
            "args": args,
            "success": result.success,
            "summary": result.summary,
            "ran_at": t0.isoformat(),
            "duration_ms": result.duration_ms,
        })
        # Keep last 100 entries
        if len(_RUN_LOG) > 100:
            _RUN_LOG.pop(0)
        return result
    except Exception as e:
        return SkillResult(
            success=False,
            output=None,
            error=str(e),
            duration_ms=int((datetime.now() - t0).total_seconds() * 1000),
        )


def get_run_log(limit: int = 20) -> list[dict]:
    return list(reversed(_RUN_LOG[-limit:]))


# ─── Auto-register all packs on import ───────────────────────────────────────

def _load_packs():
    try:
        import skills.research as _r
        _r.register_all()
    except Exception as e:
        print(f"[SKILLS] research pack load error: {e}")
    try:
        import skills.content as _c
        _c.register_all()
    except Exception as e:
        print(f"[SKILLS] content pack load error: {e}")
    try:
        import skills.google_skills as _g
        _g.register_all()
    except Exception as e:
        pass  # Optional, Google creds may not be set


_load_packs()

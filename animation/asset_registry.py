"""Manifest-backed QPixmap registry with size selection and asset fallback."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QPixmap

from .clip import (
    ActionSpec,
    Anchor,
    AnimationClip,
    AnimationPhase,
    AnimationProgram,
    ClipFrame,
    ClipSegmentSpec,
    PetAction,
)


# Actions that have a "sitting on a window edge" version (direction "edge").
EDGE_ASSETS = {
    PetAction.PERCH: "perch_sit",
    PetAction.WORKING: "perch_work",
    PetAction.PERCH_SLEEP: "perch_sleep",
}

# Actions that have bespoke screen-edge peek/work/sleep versions (direction "dock_left" / "dock_right").
DOCK_LEFT_ASSETS = {
    PetAction.IDLE: "dock_peek",
    PetAction.WORKING: "dock_work",
    PetAction.DOCK_SLEEP: "dock_sleep",
}
DOCK_RIGHT_ASSETS = {
    PetAction.IDLE: "dock_peek_right",
    PetAction.WORKING: "dock_work_right",
    PetAction.DOCK_SLEEP: "dock_sleep_right",
}
BESPOKE_DOCK_ASSETS = frozenset(
    (*DOCK_LEFT_ASSETS.values(), *DOCK_RIGHT_ASSETS.values())
)


class AssetRegistry:
    def __init__(self, assets_dir: Path, *, base_manifest: Path | None = None) -> None:
        """Load a character manifest.

        ``assets_dir`` is either a classic ``assets`` folder or a character
        folder (``carbon/``, ``neon/``...).  Character manifests only describe
        frames; their ``actions``/``fallbacks`` come from ``base_manifest``.
        Frame paths are written as ``assets/processed/...`` and are resolved
        relative to the character folder when that folder holds them.
        """
        self.assets_dir = Path(assets_dir)
        self.project_root = self.assets_dir.parent
        manifest_path = self.assets_dir / "manifests" / "actions.json"
        self.manifest_path = manifest_path
        try:
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            raise RuntimeError(f"无法读取动作清单：{manifest_path}") from error
        if base_manifest is not None:
            try:
                base = json.loads(Path(base_manifest).read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as error:
                raise RuntimeError(f"无法读取基础动作清单：{base_manifest}") from error
            if "actions" not in self.manifest and "actions" in base:
                self.manifest["actions"] = base["actions"]
            # A character may override individual fallbacks; base fills the rest.
            self.manifest["fallbacks"] = {**base.get("fallbacks", {}), **self.manifest.get("fallbacks", {})}
            self.manifest["frame_pick"] = {**base.get("frame_pick", {}), **self.manifest.get("frame_pick", {})}
        self.character_id = str(self.manifest.get("character_id", self.assets_dir.name))
        self._assets = self.manifest.get("assets", {})
        self.specs = self._parse_specs()
        self._frame_cache: dict[tuple[str, int], tuple[ClipFrame, ...]] = {}

    def _parse_specs(self) -> dict[PetAction, ActionSpec]:
        raw_actions = self.manifest.get("actions", {})
        specs: dict[PetAction, ActionSpec] = {}
        for raw_name, raw in raw_actions.items():
            if not isinstance(raw, dict):
                continue
            action = PetAction.coerce(raw.get("id", raw_name))
            anchor_raw = raw.get("anchor", {})
            if not isinstance(anchor_raw, dict):
                anchor_raw = {}
            transition_raw = raw.get("transition", {})
            if not isinstance(transition_raw, dict):
                transition_raw = {}
            specs[action] = ActionSpec(
                action=action,
                asset_id=str(raw["asset"]),
                loop=bool(raw.get("loop", False)),
                duration_ms=raw.get("duration_ms") if isinstance(raw.get("duration_ms"), int) else None,
                priority=int(raw.get("priority", 0)),
                interruptible=bool(raw.get("interruptible", True)),
                return_state=PetAction.coerce(raw.get("return_state", "IDLE")),
                anchor=Anchor(
                    kind=str(anchor_raw.get("type", "ground")),
                    x=float(anchor_raw.get("x", 0.5)),
                    y=float(anchor_raw.get("y", 0.985)),
                ),
                effect=str((raw.get("procedural_motion") or {}).get("type", "breath")),
                quality=str(raw.get("quality", "placeholder")),
                requires_real_frames=bool(raw.get("requires_real_frames", False)),
                enter=self._parse_segment(transition_raw.get("enter")),
                exit=self._parse_segment(transition_raw.get("exit")),
                frame_ms=raw.get("frame_ms") if isinstance(raw.get("frame_ms"), int) and raw.get("frame_ms") > 0 else None,
            )
        return specs

    @staticmethod
    def _parse_segment(raw: object) -> ClipSegmentSpec | None:
        if not isinstance(raw, dict) or not raw.get("asset"):
            return None
        duration = raw.get("duration_ms")
        if not isinstance(duration, int) or duration <= 0:
            return None
        effect = raw.get("effect")
        return ClipSegmentSpec(
            asset_id=str(raw["asset"]),
            duration_ms=duration,
            effect=str(effect) if effect else None,
        )

    def clip_for(self, action: PetAction | str, *, height: int, direction: str) -> AnimationClip:
        action = PetAction.coerce(action)
        spec = self.specs[action]
        asset_id = self._asset_for(action, spec.asset_id, direction)
        frames, selected_size = self._frames_for(asset_id, height)
        resolved_asset = self.resolve_asset_id(asset_id)
        frame_duration = self._frame_duration_ms(spec, len(frames), resolved_asset)
        return AnimationClip(
            action=action,
            asset_id=resolved_asset,
            frames=frames,
            loop=spec.loop,
            duration_ms=spec.duration_ms,
            frame_duration_ms=frame_duration,
            anchor=spec.anchor,
            effect=spec.effect,
            quality=spec.quality,
            requires_real_frames=spec.requires_real_frames,
            # Left and right locomotion art is authored independently.
            mirrored=self._should_mirror(asset_id, direction),
            cycle=spec.frame_ms is not None and len(frames) > 1,
        )

    def program_for(self, action: PetAction | str, *, height: int, direction: str) -> AnimationProgram:
        action = PetAction.coerce(action)
        spec = self.specs[action]
        body = self.clip_for(action, height=height, direction=direction)
        return AnimationProgram(
            action=action,
            body=body,
            enter=self._segment_clip(spec, spec.enter, AnimationPhase.ENTER, height, direction),
            exit=self._segment_clip(spec, spec.exit, AnimationPhase.EXIT, height, direction),
        )

    def _segment_clip(
        self,
        spec: ActionSpec,
        segment: ClipSegmentSpec | None,
        phase: AnimationPhase,
        height: int,
        direction: str,
    ) -> AnimationClip | None:
        if segment is None:
            return None
        asset_id = self._directional_transition_asset(segment.asset_id, direction)
        resolved_asset = self.resolve_asset_id(asset_id)
        frames, _selected_size = self._frames_for(resolved_asset, height)
        return AnimationClip(
            action=spec.action,
            asset_id=resolved_asset,
            frames=frames,
            loop=False,
            duration_ms=segment.duration_ms,
            frame_duration_ms=max(55, segment.duration_ms // max(1, len(frames))),
            anchor=spec.anchor,
            effect=segment.effect or spec.effect,
            quality=spec.quality,
            requires_real_frames=spec.requires_real_frames,
            mirrored=self._should_mirror(segment.asset_id, direction),
            phase=phase,
        )

    @staticmethod
    def _should_mirror(asset_id: str, direction: str) -> bool:
        # Directional walking art is authored separately so asymmetric hair,
        # bow and apron details never jump sides.
        return False

    @staticmethod
    def _directional_transition_asset(asset_id: str, direction: str) -> str:
        if direction == "right" and asset_id.endswith("_left"):
            return asset_id[:-5] + "_right"
        return asset_id

    @staticmethod
    def _asset_for(action: PetAction, default_asset: str, direction: str) -> str:
        if direction == "dock_left" and action in DOCK_LEFT_ASSETS:
            return DOCK_LEFT_ASSETS[action]
        if direction == "dock_right" and action in DOCK_RIGHT_ASSETS:
            return DOCK_RIGHT_ASSETS[action]
        if action in {PetAction.IDLE, PetAction.THINKING}:
            return "idle_back" if direction == "up" else ("idle_think" if action == PetAction.THINKING else "idle_front")
        if action == PetAction.WALKING:
            if direction == "up":
                return "idle_back"
            if direction == "down":
                return "idle_front"
            if direction == "right":
                return "walk_side_right"
        if action == PetAction.CLIMBING and direction == "right":
            return "climb_side_right"
        if direction == "edge" and action in EDGE_ASSETS:
            # On a window's top edge: sitting with the legs over the edge.
            return EDGE_ASSETS[action]
        return default_asset

    def resolve_asset_id(self, asset_id: str) -> str:
        """Follow ``fallbacks`` until an asset with frames exists (cycle-safe)."""
        fallbacks = self.manifest.get("fallbacks") or {}
        seen: set[str] = set()
        current = asset_id
        while not self.has_real_frames(current) and current in fallbacks and current not in seen:
            seen.add(current)
            current = str(fallbacks[current])
        return current

    def has_real_frames(self, asset_id: str) -> bool:
        raw = self._assets.get(asset_id)
        if not isinstance(raw, dict):
            return False
        frames = raw.get("frames")
        return isinstance(frames, dict) and any(
            str(size).isdigit() and isinstance(paths, list) and bool(paths)
            for size, paths in frames.items()
        )

    def _frames_for(self, asset_id: str, height: int) -> tuple[tuple[ClipFrame, ...], int]:
        asset_id = self.resolve_asset_id(asset_id)
        raw_asset = self._assets.get(asset_id)
        if not isinstance(raw_asset, dict):
            raise RuntimeError(f"动作清单缺少素材：{asset_id}")
        frames_by_size = raw_asset.get("frames", {})
        available = sorted(int(size) for size in frames_by_size if str(size).isdigit())
        if not available:
            raise RuntimeError(f"素材 {asset_id} 没有尺寸帧")
        selected_size = min(available, key=lambda size: abs(size - height))
        cache_key = (asset_id, selected_size)
        if cache_key not in self._frame_cache:
            raw_paths = frames_by_size[str(selected_size)]
            loaded: list[ClipFrame] = []
            for raw_path in raw_paths:
                path = self._resolve_frame_path(str(raw_path))
                pixmap = QPixmap(str(path))
                if pixmap.isNull():
                    raise RuntimeError(f"无法加载动作帧：{path}")
                loaded.append(ClipFrame(path, pixmap))
            pick = (self.manifest.get("frame_pick") or {}).get(asset_id)
            if isinstance(pick, list) and loaded:
                picked = [loaded[i] for i in pick if isinstance(i, int) and 0 <= i < len(loaded)]
                loaded = picked or loaded
            self._frame_cache[cache_key] = tuple(loaded)
        return self._frame_cache[cache_key], selected_size

    def expression_names(self) -> tuple[str, ...]:
        section = self.manifest.get("expressions")
        return tuple(section) if isinstance(section, dict) else ()

    def expression_pixmap(self, name: str, height: int) -> QPixmap | None:
        """The idle frame wearing ``name``'s face, at the size nearest ``height``."""
        section = self.manifest.get("expressions")
        raw = section.get(name) if isinstance(section, dict) else None
        frames_by_size = raw.get("frames", {}) if isinstance(raw, dict) else {}
        available = sorted(int(size) for size in frames_by_size if str(size).isdigit())
        if not available:
            return None
        size = min(available, key=lambda value: abs(value - height))
        key = (f"expression:{name}", size)
        if key not in self._frame_cache:
            paths = frames_by_size.get(str(size)) or []
            pixmap = QPixmap(str(self._resolve_frame_path(str(paths[0])))) if paths else QPixmap()
            self._frame_cache[key] = (ClipFrame(Path(str(paths[0]) if paths else ""), pixmap),)
        pixmap = self._frame_cache[key][0].pixmap
        return None if pixmap.isNull() else pixmap

    def _resolve_frame_path(self, raw_path: str) -> Path:
        normalized = raw_path.replace("\\", "/")
        if normalized.startswith("assets/") and self.assets_dir.name != "assets":
            local = self.assets_dir / normalized[len("assets/"):]
            if local.exists():
                return local
        return self.project_root / normalized

    @staticmethod
    def _frame_duration_ms(spec: ActionSpec, frame_count: int, asset_id: str = "") -> int:
        if frame_count <= 0:
            return 120
        if asset_id in {"dock_peek", "dock_peek_right"}:
            return 200
        if asset_id in {"dock_work", "dock_work_right"}:
            return 220
        if spec.frame_ms is not None and frame_count > 1:
            return max(60, spec.frame_ms)
        if spec.duration_ms is not None:
            return max(70, spec.duration_ms // frame_count)
        return 120 if spec.action == PetAction.WALKING else 180

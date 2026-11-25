"""Typed data exchanged by the asset registry, state machine and renderer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtGui import QPixmap


class PetAction(str, Enum):
    IDLE = "IDLE"
    BLINK = "BLINK"
    GLANCE = "GLANCE"
    THINKING = "THINKING"
    WALKING = "WALKING"
    HAPPY = "HAPPY"
    HEAD_PAT = "HEAD_PAT"
    TALKING = "TALKING"
    ANGRY = "ANGRY"
    POKE_REACT = "POKE_REACT"
    TAIL_REACT = "TAIL_REACT"
    EATING = "EATING"
    SWEEPING = "SWEEPING"
    SLEEPING = "SLEEPING"
    DRAGGING = "DRAGGING"
    FALLING = "FALLING"
    LANDING = "LANDING"
    DIZZY = "DIZZY"
    # Antigravity companion actions.  Until dedicated art exists they render
    # through manifest ``fallbacks`` plus their own procedural effect.
    WORKING = "WORKING"
    CELEBRATE = "CELEBRATE"
    TIRED = "TIRED"
    STRETCH = "STRETCH"
    TRANSFORM = "TRANSFORM"
    WAVE = "WAVE"
    PERCH = "PERCH"
    CLIMBING = "CLIMBING"
    # Companion v3.1 high-charm actions (graceful fallbacks until art lands).
    SULK = "SULK"
    WAITING_USER = "WAITING_USER"
    JUMP_UP = "JUMP_UP"
    PET_PURR = "PET_PURR"
    PERCH_SLEEP = "PERCH_SLEEP"
    DOCK_SLEEP = "DOCK_SLEEP"
    REFUSE_FOOD = "REFUSE_FOOD"

    @classmethod
    def coerce(cls, value: "PetAction | str") -> "PetAction":
        return value if isinstance(value, cls) else cls(str(value))


@dataclass(frozen=True, slots=True)
class Anchor:
    kind: str = "ground"
    x: float = 0.5
    y: float = 0.985


class AnimationPhase(str, Enum):
    ENTER = "enter"
    BODY = "body"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class ClipSegmentSpec:
    asset_id: str
    duration_ms: int
    effect: str | None = None


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action: PetAction
    asset_id: str
    loop: bool
    duration_ms: int | None
    priority: int
    interruptible: bool
    return_state: PetAction
    anchor: Anchor
    effect: str
    quality: str
    requires_real_frames: bool
    enter: ClipSegmentSpec | None = None
    exit: ClipSegmentSpec | None = None
    frame_ms: int | None = None  # set: cycle the frames at this pace for the whole clip


@dataclass(frozen=True, slots=True)
class ClipFrame:
    source: Path
    pixmap: QPixmap


@dataclass(frozen=True, slots=True)
class AnimationClip:
    action: PetAction
    asset_id: str
    frames: tuple[ClipFrame, ...]
    loop: bool
    duration_ms: int | None
    frame_duration_ms: int
    anchor: Anchor
    effect: str
    quality: str
    requires_real_frames: bool
    mirrored: bool = False
    phase: AnimationPhase = AnimationPhase.BODY
    cycle: bool = False  # one-shot clips that still loop their frames

    @property
    def identity(self) -> tuple[object, ...]:
        return (
            self.action,
            self.asset_id,
            tuple(frame.source for frame in self.frames),
            self.mirrored,
            self.anchor,
            self.effect,
            self.phase,
        )


@dataclass(frozen=True, slots=True)
class AnimationProgram:
    """An authored action split into optional enter, body and exit clips."""

    action: PetAction
    body: AnimationClip
    enter: AnimationClip | None = None
    exit: AnimationClip | None = None

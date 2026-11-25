"""Window-top surfaces for landing, walking and attachment on Windows."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from ctypes import wintypes
from typing import Protocol

from pet.physics import PhysicsPlatform


@dataclass(frozen=True, slots=True)
class SurfaceRect:
    handle: int
    left: float
    top: float
    right: float
    bottom: float
    observed_at: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def surface_id(self) -> str:
        return f"window:{self.handle}"


@dataclass(frozen=True, slots=True)
class AttachmentUpdate:
    x: float
    y: float
    lost: bool = False


class WindowRectReader(Protocol):
    def read(self, handle: int) -> tuple[int, int, int, int] | None: ...

    def foreground_handle(self) -> int: ...

    def is_point_occluded(
        self,
        handle: int,
        x: float,
        y: float,
        *,
        ignore_handles: tuple[int, ...] | set[int] = (),
    ) -> bool: ...


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class Win32WindowRectReader:
    """Read visible extended window bounds without inspecting window content."""

    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    GW_HWNDPREV = 3

    def __init__(self) -> None:
        self.available = sys.platform == "win32"
        if not self.available:
            return
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._physical_to_logical = getattr(
            self.user32,
            "PhysicalToLogicalPointForPerMonitorDPI",
            None,
        )
        if self._physical_to_logical is not None:
            self._physical_to_logical.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.POINT),
            ]
            self._physical_to_logical.restype = wintypes.BOOL
        self._get_dpi_for_window = getattr(self.user32, "GetDpiForWindow", None)
        if self._get_dpi_for_window is not None:
            self._get_dpi_for_window.argtypes = [wintypes.HWND]
            self._get_dpi_for_window.restype = wintypes.UINT
        self._monitor_from_window = getattr(self.user32, "MonitorFromWindow", None)
        if self._monitor_from_window is not None:
            self._monitor_from_window.argtypes = [wintypes.HWND, wintypes.DWORD]
            self._monitor_from_window.restype = wintypes.HMONITOR
        self._get_monitor_info = getattr(self.user32, "GetMonitorInfoW", None)
        if self._get_monitor_info is not None:
            self._get_monitor_info.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
            self._get_monitor_info.restype = wintypes.BOOL
        try:
            self.dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
            self.dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
        except OSError:
            self.dwmapi = None

    def read(self, handle: int) -> tuple[int, int, int, int] | None:
        if not self.available or not handle:
            return None
        hwnd = wintypes.HWND(int(handle))
        if not self.user32.IsWindow(hwnd):
            return None
        if not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd):
            return None
        rect = wintypes.RECT()
        if self.dwmapi is not None:
            result = self.dwmapi.DwmGetWindowAttribute(
                hwnd,
                self.DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if result != 0:
                rect = wintypes.RECT()
        if rect.right <= rect.left or rect.bottom <= rect.top:
            if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
        return self._logical_rect(hwnd, rect)

    def list_windows(self) -> list[int]:
        """Visible, ordinary top-level windows of other apps, topmost first."""
        if not self.available:
            return []
        own_pid = os.getpid()
        found: list[int] = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd, _lparam):
            try:
                if not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd):
                    return True
                if self.user32.GetWindowTextLengthW(hwnd) <= 0:
                    return True
                ex_style = self.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
                if ex_style & 0x00000080:  # WS_EX_TOOLWINDOW
                    return True
                if self.user32.GetWindow(hwnd, 4):  # GW_OWNER: dialogs and popups
                    return True
                pid = wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == own_pid:
                    return True
                if self._cloaked(hwnd):  # other virtual desktops, suspended UWP
                    return True
                found.append(int(ctypes.cast(hwnd, ctypes.c_void_p).value or 0))
            except OSError:
                pass
            return True

        self.user32.EnumWindows(enum_proc(visit), 0)
        return [handle for handle in found if handle]

    def _cloaked(self, hwnd) -> bool:
        if self.dwmapi is None:
            return False
        value = wintypes.DWORD()
        result = self.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(value), ctypes.sizeof(value))
        return result == 0 and value.value != 0

    def foreground_handle(self) -> int:
        if not self.available:
            return 0
        handle = self.user32.GetForegroundWindow()
        return int(ctypes.cast(handle, ctypes.c_void_p).value or 0)

    def is_point_occluded(
        self,
        handle: int,
        x: float,
        y: float,
        *,
        ignore_handles: tuple[int, ...] | set[int] = (),
    ) -> bool:
        """Return True if another visible top-level window above ``handle`` covers ``(x, y)``."""
        if not self.available or not handle:
            return False
        hwnd = wintypes.HWND(int(handle))
        if not self.user32.IsWindow(hwnd):
            return False
        own_pid = os.getpid()
        ignored = {int(h) for h in ignore_handles if h}
        target_int = int(handle)
        seen: set[int] = {target_int}
        curr = hwnd
        for _ in range(512):
            curr = self.user32.GetWindow(curr, self.GW_HWNDPREV)
            if not curr:
                break
            curr_int = (
                int(curr)
                if isinstance(curr, int)
                else int(ctypes.cast(curr, ctypes.c_void_p).value or 0)
            )
            if not curr_int or curr_int in seen:
                break
            seen.add(curr_int)
            curr_hwnd = wintypes.HWND(curr_int)
            if curr_int in ignored:
                curr = curr_hwnd
                continue
            try:
                if not self.user32.IsWindowVisible(curr_hwnd) or self.user32.IsIconic(curr_hwnd):
                    curr = curr_hwnd
                    continue
                if self.user32.GetWindowTextLengthW(curr_hwnd) <= 0:
                    curr = curr_hwnd
                    continue
                ex_style = self.user32.GetWindowLongW(curr_hwnd, -20)  # GWL_EXSTYLE
                if ex_style & 0x00000080:  # WS_EX_TOOLWINDOW
                    curr = curr_hwnd
                    continue
                if (ex_style & 0x00080020) == 0x00080020:  # WS_EX_LAYERED | WS_EX_TRANSPARENT
                    curr = curr_hwnd
                    continue
                pid = wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(curr_hwnd, ctypes.byref(pid))
                if pid.value == own_pid:
                    curr = curr_hwnd
                    continue
                if self._cloaked(curr_hwnd):
                    curr = curr_hwnd
                    continue
                rect = self.read(curr_int)
                if rect is None:
                    curr = curr_hwnd
                    continue
                left, top, right, bottom = rect
                if (right - left) < 40 or (bottom - top) < 40:
                    curr = curr_hwnd
                    continue
                if left <= x <= right and top <= y <= bottom:
                    return True
            except OSError:
                pass
            curr = curr_hwnd
        return False

    def _monitor_origin(self, hwnd) -> tuple[int, int]:
        if self._monitor_from_window is None or self._get_monitor_info is None:
            return 0, 0
        try:
            hmonitor = self._monitor_from_window(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            if not hmonitor:
                return 0, 0
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if not self._get_monitor_info(hmonitor, ctypes.byref(info)):
                return 0, 0
            return int(info.rcMonitor.left), int(info.rcMonitor.top)
        except Exception:
            return 0, 0

    def _logical_rect(self, hwnd, rect: wintypes.RECT) -> tuple[int, int, int, int]:
        """Convert Win32 physical pixels into the device-independent space Qt uses."""

        # DWM extended bounds are always physical pixels.  Qt's QWidget and
        # QScreen APIs use device-independent coordinates, so the window DPI
        # relative to its monitor origin is the reliable conversion.
        if self._get_dpi_for_window is not None:
            dpi = int(self._get_dpi_for_window(hwnd) or 96)
            scale = max(1.0, dpi / 96.0)
            origin_x, origin_y = self._monitor_origin(hwnd)
            return (
                origin_x + round((rect.left - origin_x) / scale),
                origin_y + round((rect.top - origin_y) / scale),
                origin_x + round((rect.right - origin_x) / scale),
                origin_y + round((rect.bottom - origin_y) / scale),
            )
        if self._physical_to_logical is not None:
            top_left = wintypes.POINT(int(rect.left), int(rect.top))
            bottom_right = wintypes.POINT(int(rect.right), int(rect.bottom))
            if self._physical_to_logical(hwnd, ctypes.byref(top_left)) and self._physical_to_logical(
                hwnd, ctypes.byref(bottom_right)
            ):
                return top_left.x, top_left.y, bottom_right.x, bottom_right.y
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


class DesktopSurfaceTracker:
    """Keep only geometry needed to make a foreground window a pet surface."""

    def __init__(
        self,
        reader: WindowRectReader | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self.reader = reader or Win32WindowRectReader()
        self.enabled = bool(enabled)
        self._surfaces: dict[int, SurfaceRect] = {}
        self._candidate_handle: int | None = None
        self._attached_handle: int | None = None
        # A window the pet is deliberately jumping to; it stays a platform even
        # when it is not the foreground window.
        self._target_handle: int | None = None
        self._relative_center = 0.5
        self._next_attachment_refresh = 0.0
        # A window she just jumped off is not a platform for a moment.
        self._ignored_handle: int | None = None
        self._ignored_until = 0.0

    @property
    def attached(self) -> bool:
        return self.enabled and self._attached_handle is not None

    def set_enabled(self, enabled: bool) -> bool:
        was_attached = self.attached
        self.enabled = bool(enabled)
        if not self.enabled:
            self.detach()
        return was_attached and not self.enabled

    def observe_window(self, handle: int, *, now: float | None = None) -> bool:
        if not self.enabled or not handle:
            return False
        now = time.monotonic() if now is None else now
        surface = self._read_surface(handle, now)
        if surface is None:
            return False
        self._surfaces[handle] = surface
        self._candidate_handle = handle
        return True

    def observe_foreground(
        self,
        *,
        ignored_handles: set[int] | None = None,
        now: float | None = None,
    ) -> bool:
        foreground = getattr(self.reader, "foreground_handle", None)
        handle = int(foreground()) if callable(foreground) else 0
        if not handle or handle in (ignored_handles or set()):
            return False
        return self.observe_window(handle, now=now)

    @staticmethod
    def _resolve_work_area_top(
        work_area_top: float | Callable[[SurfaceRect], float] | None,
        surface: SurfaceRect,
    ) -> float | None:
        if work_area_top is None:
            return None
        if callable(work_area_top):
            return float(work_area_top(surface))
        return float(work_area_top)

    def physics_platforms(
        self,
        *,
        work_area_top: float | Callable[[SurfaceRect], float],
        widget_height: float,
        now: float | None = None,
    ) -> tuple[PhysicsPlatform, ...]:
        if not self.enabled:
            return ()
        now = time.monotonic() if now is None else now
        handles = {self._candidate_handle, self._attached_handle, self._target_handle}
        platforms: list[PhysicsPlatform] = []
        for handle in handles:
            if handle is None:
                continue
            if handle == self._ignored_handle and now < self._ignored_until:
                continue
            surface = self._surfaces.get(handle)
            if surface is None:
                continue
            if handle != self._attached_handle and now - surface.observed_at > 30.0:
                continue
            if surface.width < 180.0 or surface.height < 120.0:
                continue
            ceiling = self._resolve_work_area_top(work_area_top, surface)
            if ceiling is not None and surface.top - widget_height < ceiling:
                continue
            platforms.append(
                PhysicsPlatform(
                    left=surface.left + 8.0,
                    right=surface.right - 8.0,
                    top=surface.top,
                    surface_id=surface.surface_id,
                )
            )
        return tuple(platforms)

    def attach(
        self,
        surface_id: str | None,
        *,
        widget_x: float,
        widget_width: float,
        widget_height: float | None = None,
        work_area_top: float | Callable[[SurfaceRect], float] | None = None,
    ) -> bool:
        handle = self._handle_from_id(surface_id)
        surface = self._surfaces.get(handle) if handle is not None else None
        if not self.enabled or surface is None or surface.width <= 0.0:
            self.detach()
            return False
        if widget_height is not None and work_area_top is not None:
            ceiling = self._resolve_work_area_top(work_area_top, surface)
            if ceiling is not None and surface.top - widget_height < ceiling:
                self.detach()
                return False
        center = widget_x + widget_width / 2.0
        self._relative_center = max(0.0, min(1.0, (center - surface.left) / surface.width))
        self._attached_handle = handle
        self._next_attachment_refresh = 0.0
        return True

    def set_target(self, handle: int | None, *, now: float | None = None) -> bool:
        """Pin ``handle`` as a landing platform (None clears it)."""
        self._target_handle = None
        if handle is None or not self.enabled:
            return False
        now = time.monotonic() if now is None else now
        surface = self._read_surface(handle, now)
        if surface is None:
            return False
        self._surfaces[handle] = surface
        self._target_handle = handle
        return True

    @property
    def attached_handle(self) -> int | None:
        return self._attached_handle if self.attached else None

    def detach(self) -> None:
        self._attached_handle = None
        self._relative_center = 0.5
        self._next_attachment_refresh = 0.0

    def follow_attachment(
        self,
        *,
        now: float,
        widget_x: float,
        widget_width: float,
        widget_height: float,
        sink: float = 0.0,
        work_area_top: float | Callable[[SurfaceRect], float] | None = None,
        pet_x: float | None = None,
        ignore_handles: tuple[int, ...] | set[int] = (),
    ) -> AttachmentUpdate | None:
        """Where the widget goes to stay on the attached window.

        ``sink`` lowers her below the top edge (sitting with legs hanging over).
        """
        if not self.attached or self._attached_handle is None:
            return None
        if now < self._next_attachment_refresh:
            return None
        self._next_attachment_refresh = now + 0.08
        surface = self._read_surface(self._attached_handle, now)
        if surface is None:
            self.detach()
            return AttachmentUpdate(widget_x, 0.0, lost=True)
        ceiling = self._resolve_work_area_top(work_area_top, surface)
        if ceiling is not None and surface.top - widget_height < ceiling:
            self.ignore_platform(surface.handle, seconds=2.0, now=now)
            self.detach()
            return AttachmentUpdate(widget_x, ceiling, lost=True)
        self._surfaces[surface.handle] = surface
        target_center = surface.left + surface.width * self._relative_center
        target_x = target_center - widget_width / 2.0
        lower, upper = self._movement_bounds_for(surface, widget_width)
        target_x = max(lower, min(upper, target_x))
        occluded_fn = getattr(self.reader, "is_point_occluded", None)
        if callable(occluded_fn):
            foot_x = float(pet_x) if pet_x is not None else (target_x + widget_width / 2.0)
            foot_y = min(surface.bottom, surface.top + 2.0)
            if occluded_fn(surface.handle, foot_x, foot_y, ignore_handles=ignore_handles):
                self.ignore_platform(surface.handle, seconds=2.0, now=now)
                self.detach()
                return AttachmentUpdate(widget_x, surface.top - widget_height + sink, lost=True)
        return AttachmentUpdate(target_x, surface.top - widget_height + sink)

    def ignore_platform(self, handle: int | None, *, seconds: float = 3.0, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._ignored_handle = handle
        self._ignored_until = now + seconds

    def nearby_windows(self, *, now: float | None = None) -> list[SurfaceRect]:
        """Bounds of the visible app windows, topmost first (empty if unknown)."""
        lister = getattr(self.reader, "list_windows", None)
        if not self.enabled or not callable(lister):
            return []
        now = time.monotonic() if now is None else now
        out: list[SurfaceRect] = []
        for handle in lister():
            surface = self._read_surface(int(handle), now)
            if surface is not None:
                out.append(surface)
        return out

    def refresh_soon(self) -> None:
        """Re-read the attached window on the next follow (e.g. pose changed)."""
        self._next_attachment_refresh = 0.0

    @property
    def candidate_handle(self) -> int | None:
        return self._candidate_handle if self.enabled else None

    def read_rect(self, handle: int, *, now: float | None = None) -> SurfaceRect | None:
        """Fresh bounds of ``handle`` (None if gone, minimized or too small)."""
        if not self.enabled or not handle:
            return None
        now = time.monotonic() if now is None else now
        surface = self._read_surface(handle, now)
        if surface is not None:
            self._surfaces[handle] = surface
        return surface

    def record_pet_position(self, *, widget_x: float, widget_width: float) -> None:
        if not self.attached or self._attached_handle is None:
            return
        surface = self._surfaces.get(self._attached_handle)
        if surface is None or surface.width <= 0.0:
            return
        center = widget_x + widget_width / 2.0
        self._relative_center = max(0.0, min(1.0, (center - surface.left) / surface.width))

    def movement_bounds(self, *, widget_width: float) -> tuple[float, float] | None:
        if not self.attached or self._attached_handle is None:
            return None
        surface = self._surfaces.get(self._attached_handle)
        if surface is None:
            return None
        return self._movement_bounds_for(surface, widget_width)

    @staticmethod
    def _movement_bounds_for(surface: SurfaceRect, widget_width: float) -> tuple[float, float]:
        foot_margin = min(38.0, max(18.0, surface.width * 0.055))
        lower = surface.left + foot_margin - widget_width / 2.0
        upper = surface.right - foot_margin - widget_width / 2.0
        return lower, max(lower, upper)

    def _read_surface(self, handle: int, now: float) -> SurfaceRect | None:
        rect = self.reader.read(handle)
        if rect is None:
            return None
        left, top, right, bottom = rect
        surface = SurfaceRect(handle, float(left), float(top), float(right), float(bottom), now)
        if surface.width < 180.0 or surface.height < 120.0:
            return None
        return surface

    @staticmethod
    def _handle_from_id(surface_id: str | None) -> int | None:
        if not surface_id or not surface_id.startswith("window:"):
            return None
        try:
            return int(surface_id.partition(":")[2])
        except ValueError:
            return None

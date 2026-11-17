# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
"""Read and operate Windows apps through UI Automation, with every call checked by the policy and logged."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import AuditLog
from .policy import Denied, Policy

MAX_ELEMENTS = 400  # keeps one window read inside an agent's context
MAX_VALUE = 200


def _desktop() -> Any:
    from pywinauto import Desktop  # imported late so policy and audit work, and are testable, off Windows

    return Desktop(backend="uia")


def _app_name(pid: int) -> str:
    from pywinauto.application import process_module

    try:
        return Path(process_module(pid)).name.lower()
    except Exception:  # protected or already-exited process: treat as unknown, which is never allowed
        return "unknown"


def _is_password(element: Any) -> bool:
    try:
        return bool(element.element_info.element.CurrentIsPassword)
    except Exception:  # if we cannot tell, assume it is one
        return True


def _text(element: Any) -> str:
    if element.element_info.control_type == "Edit":
        return element.get_value()[:MAX_VALUE]
    return element.iface_text.DocumentRange.GetText(MAX_VALUE)  # "Document": Notepad, Word, rich text


TEXT_TYPES = ("Edit", "Document")


class Pointman:
    def __init__(self, policy: Policy, audit: AuditLog):
        self.policy = policy
        self.audit = audit
        self._elements: dict[int, list[Any]] = {}  # window handle -> elements from its last read

    def _window(self, handle: int) -> tuple[Any, str]:
        for window in _desktop().windows():
            if window.handle == handle:
                return window, _app_name(window.process_id())
        raise Denied(f"no window with handle {handle}; call list_windows again")

    def _element(self, handle: int, ref: str) -> Any:
        elements = self._elements.get(handle)
        if elements is None:
            raise Denied("call read_window for this window first")
        try:
            return elements[int(ref.removeprefix("e")) - 1]
        except (ValueError, IndexError):
            raise Denied(f"no element {ref} in the last read of this window") from None

    def _run(self, tool: str, detail: dict, work: Any) -> Any:
        """Run `work`, log the outcome, and turn refusals into text the agent can read."""
        try:
            result = work()
        except Denied as e:
            self.audit.record(tool, "denied", reason=str(e), **detail)
            return f"DENIED: {e}"
        except Exception as e:
            self.audit.record(tool, "error", reason=repr(e), **detail)
            return f"ERROR: {e!r}"
        self.audit.record(tool, "ok", **detail)
        return result

    def list_windows(self) -> str:
        """Open windows. Titles are shown only for allowed apps, because titles leak document and email names."""

        def work() -> str:
            if self.policy.kill_switch.exists():
                raise Denied(f"stopped: the kill switch file {self.policy.kill_switch} exists")
            lines = []
            for window in _desktop().windows():
                if not window.is_visible() or not window.window_text():
                    continue
                app = _app_name(window.process_id())
                title = window.window_text() if self.policy.allows(app) else "(not allowed)"
                lines.append(f"{window.handle} {app} {title!r}")
            return "\n".join(lines) or "no windows"

        return self._run("list_windows", {}, work)

    def read_window(self, handle: int) -> str:
        """The window's controls, one per line, each with a ref (e1, e2, ...) for click and set_text."""
        detail: dict = {"handle": handle}

        def work() -> str:
            window, app = self._window(handle)
            detail["app"] = app
            self.policy.check_read(app)
            elements = window.descendants()[:MAX_ELEMENTS]
            self._elements[handle] = elements
            lines = [f"{app} {window.window_text()!r}"]
            for number, element in enumerate(elements, 1):
                info = element.element_info
                line = f"e{number} {info.control_type} {info.name!r}"
                if info.control_type in TEXT_TYPES:
                    if _is_password(element):
                        line += " value=(password, hidden)"
                    else:
                        line += f" value={_text(element)!r}"
                lines.append(line)
            return "\n".join(lines)

        return self._run("read_window", detail, work)

    def click(self, handle: int, ref: str) -> str:
        """Press a button or other control from the last read_window."""
        detail: dict = {"handle": handle, "ref": ref}

        def work() -> str:
            window, app = self._window(handle)
            detail["app"] = app
            self.policy.check_action(app)
            element = self._element(handle, ref)
            detail["target"] = f"{element.element_info.control_type} {element.element_info.name!r}"
            element.invoke()
            return f"clicked {detail['target']}"

        return self._run("click", detail, work)

    def set_text(self, handle: int, ref: str, text: str) -> str:
        """Replace the contents of a text box from the last read_window. Password boxes are refused."""
        detail: dict = {"handle": handle, "ref": ref, "length": len(text)}  # the text itself is not logged

        def work() -> str:
            window, app = self._window(handle)
            detail["app"] = app
            self.policy.check_action(app)
            element = self._element(handle, ref)
            detail["target"] = f"{element.element_info.control_type} {element.element_info.name!r}"
            if _is_password(element):
                raise Denied("this is a password box; a person has to type into it")
            if element.element_info.control_type != "Edit":
                raise Denied("only Edit boxes can be set; this is a " + element.element_info.control_type)
            element.set_edit_text(text)
            return f"set {detail['target']}"

        return self._run("set_text", detail, work)

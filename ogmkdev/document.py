"""An open document: text, EditorConfig settings, language and diagnostics. No GUI code here."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import diagnostics, editing, editorconfig, languages
from .diagnostics import Diagnostic


@dataclass
class Document:
    path: Optional[str]
    text: str = ""
    settings: editorconfig.EditorSettings = field(default_factory=editorconfig.EditorSettings)
    detection: languages.Detection = field(default_factory=lambda: languages.detect("untitled.txt"))
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @classmethod
    def open(cls, path: str, properties: Optional[Dict[str, str]] = None) -> "Document":
        """Open a file. ``properties`` are the effective settings (global and project); the file's
        own EditorConfig files are used when they are not given."""
        absolute = os.path.abspath(path)
        with open(absolute, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        if properties is None:
            properties = editorconfig.effective_properties(absolute)
        settings = editorconfig.settings_from_properties(properties)
        detection = languages.detect_file(absolute, settings.custom)
        document = cls(absolute, text, settings, detection)
        document.analyze()
        return document

    @classmethod
    def new(cls, name: str = "untitled.txt") -> "Document":
        document = cls(None, "", editorconfig.EditorSettings(), languages.detect(name))
        document.analyze()
        return document

    @property
    def title(self) -> str:
        return os.path.basename(self.path) if self.path else "untitled"

    def analyze(self) -> List[Diagnostic]:
        self.diagnostics = diagnostics.analyze(self.text, self.detection, self.settings)
        return self.diagnostics

    def save(self, path: Optional[str] = None) -> None:
        """Write the text with EditorConfig line handling. ``path`` makes this a save-as."""
        target = os.path.abspath(path or self.path or "")
        if not (path or self.path):
            raise ValueError("document has no path yet")
        with open(target, "wb") as handle:
            handle.write(editing.encode_for_save(self.text, self.settings))
        self.path = target
        self.settings = editorconfig.settings_for(target)
        self.detection = languages.detect_file(target, self.settings.custom)
        self.analyze()

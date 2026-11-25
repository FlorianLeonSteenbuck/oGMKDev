"""Editor settings applied to text before it is saved (GUI-independent)."""

from __future__ import annotations

from .editorconfig import EditorSettings


def prepare_for_save(text: str, settings: EditorSettings) -> str:
    """Apply EditorConfig line handling: trailing whitespace, final newline, line endings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if settings.trim_trailing_whitespace:
        text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    if settings.insert_final_newline and text.strip():
        text = text.rstrip("\n") + "\n"
    eol = {"crlf": "\r\n", "cr": "\r"}.get(settings.end_of_line or "lf", "\n")
    return text.replace("\n", eol)


def encode_for_save(text: str, settings: EditorSettings) -> bytes:
    """Bytes for the file, honouring ``charset`` (utf-8-bom adds the BOM)."""
    prepared = prepare_for_save(text, settings)
    if settings.charset == "utf-8-bom":
        return b"\xef\xbb\xbf" + prepared.encode("utf-8")
    if settings.charset == "utf-16le":
        return prepared.encode("utf-16-le")
    if settings.charset == "utf-16be":
        return prepared.encode("utf-16-be")
    if settings.charset == "latin1":
        return prepared.encode("latin-1", errors="replace")
    return prepared.encode("utf-8")


def indent_unit(settings: EditorSettings) -> str:
    """The text inserted for one indent level."""
    if settings.indent_style == "tab":
        return "\t"
    return " " * (settings.indent_size or 4)

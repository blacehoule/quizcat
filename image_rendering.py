"""Terminal image renderer selection for QuizCat."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from textual_image.renderable import sixel, tgp
from textual_image.renderable.halfcell import Image as HalfcellRenderable
from textual_image.renderable.tgp import Image as TGPRenderable
from textual_image.renderable.unicode import Image as UnicodeRenderable
from textual_image.widget._base import Image as BaseImage
from textual_image.widget.sixel import Image as SixelImage


class TGPImage(BaseImage, Renderable=TGPRenderable):
    """Textual widget for the kitty terminal graphics protocol."""


class HalfcellImage(BaseImage, Renderable=HalfcellRenderable):
    """Textual widget for low-resolution half-cell rendering."""


class UnicodeImage(BaseImage, Renderable=UnicodeRenderable):
    """Textual widget for monochrome unicode rendering."""


ImageWidgetClass = type[BaseImage]


@dataclass(frozen=True)
class QuestionImageRenderer:
    """Selected renderer for question images."""

    name: str
    widget_class: ImageWidgetClass | None
    native_pixels: bool
    unavailable_reason: str = ""


NATIVE_IMAGE_UNAVAILABLE = (
    "Native terminal image support unavailable. Use a sixel or kitty-graphics "
    "terminal, or set QUIZCAT_IMAGE_RENDERER=halfcell for a low-resolution "
    "fallback."
)


def select_question_image_renderer(
    preferred: str | None = None,
) -> QuestionImageRenderer:
    """Choose the renderer used for question images.

    Native renderers preserve the PNG's pixel dimensions. Half-cell and unicode
    renderers resample images down to terminal character cells, so they are only
    used when explicitly requested.
    """

    renderer = (preferred or os.environ.get("QUIZCAT_IMAGE_RENDERER", "auto"))
    renderer = renderer.strip().lower()

    match renderer:
        case "auto" | "native" | "":
            return _select_native_renderer()
        case "sixel":
            return QuestionImageRenderer("sixel", SixelImage, native_pixels=True)
        case "tgp" | "kitty":
            return QuestionImageRenderer("tgp", TGPImage, native_pixels=True)
        case "halfcell":
            return QuestionImageRenderer(
                "halfcell",
                HalfcellImage,
                native_pixels=False,
            )
        case "unicode":
            return QuestionImageRenderer(
                "unicode",
                UnicodeImage,
                native_pixels=False,
            )
        case "off" | "none":
            return QuestionImageRenderer(
                "off",
                None,
                native_pixels=False,
                unavailable_reason=NATIVE_IMAGE_UNAVAILABLE,
            )
        case _:
            return QuestionImageRenderer(
                "unavailable",
                None,
                native_pixels=False,
                unavailable_reason=(
                    f"Unknown QUIZCAT_IMAGE_RENDERER={renderer!r}. "
                    f"{NATIVE_IMAGE_UNAVAILABLE}"
                ),
            )


def _select_native_renderer() -> QuestionImageRenderer:
    if not _stdout_is_tty():
        return QuestionImageRenderer(
            "unavailable",
            None,
            native_pixels=False,
            unavailable_reason=NATIVE_IMAGE_UNAVAILABLE,
        )

    if _terminal_supports_sixel():
        return QuestionImageRenderer("sixel", SixelImage, native_pixels=True)

    if _terminal_supports_tgp():
        return QuestionImageRenderer("tgp", TGPImage, native_pixels=True)

    return QuestionImageRenderer(
        "unavailable",
        None,
        native_pixels=False,
        unavailable_reason=NATIVE_IMAGE_UNAVAILABLE,
    )


def _stdout_is_tty() -> bool:
    return bool(sys.__stdout__ and sys.__stdout__.isatty())


def _terminal_supports_sixel() -> bool:
    try:
        return sixel.query_terminal_support()
    except Exception:
        return False


def _terminal_supports_tgp() -> bool:
    try:
        return tgp.query_terminal_support()
    except Exception:
        return False

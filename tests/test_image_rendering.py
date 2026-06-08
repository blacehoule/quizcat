from __future__ import annotations

import unittest
from unittest.mock import patch

from image_rendering import (
    HalfcellImage,
    QuestionImageRenderer,
    SixelImage,
    TGPImage,
    select_question_image_renderer,
)


class ImageRenderingTests(unittest.TestCase):
    def test_auto_prefers_native_sixel_renderer(self) -> None:
        with (
            patch("image_rendering._stdout_is_tty", return_value=True),
            patch("image_rendering._terminal_supports_sixel", return_value=True),
            patch("image_rendering._terminal_supports_tgp", return_value=False),
        ):
            renderer = select_question_image_renderer("auto")

        self.assertEqual(QuestionImageRenderer("sixel", SixelImage, True), renderer)

    def test_auto_uses_tgp_when_sixel_is_unavailable(self) -> None:
        with (
            patch("image_rendering._stdout_is_tty", return_value=True),
            patch("image_rendering._terminal_supports_sixel", return_value=False),
            patch("image_rendering._terminal_supports_tgp", return_value=True),
        ):
            renderer = select_question_image_renderer("auto")

        self.assertEqual(QuestionImageRenderer("tgp", TGPImage, True), renderer)

    def test_auto_does_not_fall_back_to_halfcell(self) -> None:
        with (
            patch("image_rendering._stdout_is_tty", return_value=True),
            patch("image_rendering._terminal_supports_sixel", return_value=False),
            patch("image_rendering._terminal_supports_tgp", return_value=False),
        ):
            renderer = select_question_image_renderer("auto")

        self.assertIsNone(renderer.widget_class)
        self.assertFalse(renderer.native_pixels)

    def test_halfcell_requires_explicit_selection(self) -> None:
        renderer = select_question_image_renderer("halfcell")

        self.assertEqual(QuestionImageRenderer("halfcell", HalfcellImage, False), renderer)


if __name__ == "__main__":
    unittest.main()

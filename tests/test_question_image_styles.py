from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class QuestionImageStyleTests(unittest.TestCase):
    def test_question_image_style_does_not_force_scaling(self) -> None:
        stylesheet = (PROJECT_ROOT / "quizcat.tcss").read_text()

        for selector in ("QuestionImageDisplay", "#question-image"):
            declarations = _declarations_for_selector(stylesheet, selector)
            self.assertNotIn("width", declarations)
            self.assertNotIn("height", declarations)


def _declarations_for_selector(stylesheet: str, selector: str) -> set[str]:
    if f"{selector} {{" not in stylesheet:
        return set()

    rule_start = stylesheet.index(f"{selector} {{") + len(f"{selector} {{")
    rule_end = stylesheet.index("}", rule_start)
    rule_body = stylesheet[rule_start:rule_end]

    return {
        line.split(":", 1)[0].strip()
        for line in rule_body.splitlines()
        if ":" in line
    }


if __name__ == "__main__":
    unittest.main()

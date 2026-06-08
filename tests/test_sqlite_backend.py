from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from services import (
    create_quiz_service,
    format_question_content,
    format_question_markdown,
)
from storage import (
    DEFAULT_CSV_PATH,
    SeedValidationError,
    validate_seed_row,
)


class SQLiteBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "quizcat.sqlite3"
        self.service = create_quiz_service(
            db_path=self.db_path,
            seed_csv_path=DEFAULT_CSV_PATH,
        )

    def tearDown(self) -> None:
        self.service.close()
        self._temp_dir.cleanup()

    def test_seed_creates_eight_source_exam_tests(self) -> None:
        tests = self.service.list_tests()

        self.assertEqual(8, len(tests))
        self.assertEqual([f"Sample Exam {n}" for n in range(1, 9)], [
            test.title for test in tests
        ])
        self.assertTrue(all(test.question_count == 50 for test in tests))
        self.assertTrue(all(test.time_limit_seconds == 900 for test in tests))

    def test_questions_do_not_store_redundant_image_filename_column(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            columns = [
                row[1]
                for row in connection.execute("PRAGMA table_info(questions)")
            ]
            image_row = connection.execute(
                """
                SELECT stimulus, stimulus_type
                FROM questions
                WHERE stimulus_type = 'image'
                LIMIT 1
                """
            ).fetchone()

        self.assertNotIn("image_filename", columns)
        self.assertIsNotNone(image_row)
        self.assertEqual("image", image_row[1])
        self.assertTrue(image_row[0].endswith(".png"))

    def test_seed_import_is_idempotent(self) -> None:
        self.service.close()
        self.service = create_quiz_service(
            db_path=self.db_path,
            seed_csv_path=DEFAULT_CSV_PATH,
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            question_count = connection.execute(
                "SELECT COUNT(*) FROM questions"
            ).fetchone()[0]
            choice_count = connection.execute(
                "SELECT COUNT(*) FROM choices"
            ).fetchone()[0]
            test_question_count = connection.execute(
                "SELECT COUNT(*) FROM test_questions"
            ).fetchone()[0]

        self.assertEqual(400, question_count)
        self.assertEqual(400, test_question_count)
        self.assertEqual(1952, choice_count)

    def test_choices_preserve_labels_and_missing_d_e_choices(self) -> None:
        test = self.service.get_test(self.service.list_tests()[0].id)
        three_choice_question = next(
            question for question in test.questions if len(question.choices) == 3
        )

        self.assertEqual(("A", "B", "C"), tuple(
            choice.label for choice in three_choice_question.choices
        ))
        self.assertEqual((1, 2, 3), tuple(
            choice.position for choice in three_choice_question.choices
        ))

    def test_attempt_records_per_question_answer_and_score(self) -> None:
        test = self.service.get_test(self.service.list_tests()[0].id)
        attempt = self.service.start_attempt(test.id, len(test.questions))
        first_question = test.questions[0]
        second_question = test.questions[1]
        wrong_second_choice = next(
            choice.label
            for choice in second_question.choices
            if choice.label != second_question.correct_choice_label
        )

        first_answer = self.service.submit_answer(
            attempt_id=attempt.id,
            question=first_question,
            question_position=1,
            selected_choice_label=first_question.correct_choice_label,
            elapsed_seconds=5.0,
        )
        second_answer = self.service.submit_answer(
            attempt_id=attempt.id,
            question=second_question,
            question_position=2,
            selected_choice_label=wrong_second_choice,
            elapsed_seconds=10.0,
        )
        result = self.service.finish_attempt(
            attempt_id=attempt.id,
            status="completed",
            elapsed_seconds=10.0,
            total_questions=len(test.questions),
        )

        self.assertTrue(first_answer.is_correct)
        self.assertFalse(second_answer.is_correct)
        self.assertEqual(2, result.answered_count)
        self.assertEqual(1, result.correct_count)
        self.assertEqual(50, result.total_questions)

    def test_image_seed_row_requires_image_filename_to_match_stimulus(self) -> None:
        row = {
            "question_id": "img-1",
            "source_exam": "1",
            "source_file": "source.html",
            "source_category": "CCAT Spatial",
            "source_question_number": "1",
            "category": "Spatial Reasoning",
            "question_type": "Odd One Out",
            "prompt": "Which one does not belong?",
            "stimulus": "actual.png",
            "stimulus_type": "image",
            "image_filename": "other.png",
            "choice_a": "A",
            "choice_b": "B",
            "choice_c": "C",
            "choice_d": "",
            "choice_e": "",
            "correct_choice_label": "A",
            "correct_choice_text": "A",
            "explanation": "",
        }

        with self.assertRaises(SeedValidationError):
            validate_seed_row(row)

    def test_image_question_content_resolves_image_asset_path(self) -> None:
        image_dir = DEFAULT_CSV_PATH.parent / "images"
        test = self.service.get_test(self.service.list_tests()[0].id)
        image_question = next(
            question for question in test.questions if question.stimulus_type == "image"
        )

        content = format_question_content(
            image_question,
            image_asset_dir=image_dir,
        )

        self.assertEqual(image_dir / image_question.stimulus, content.image_path)
        self.assertIn(image_question.prompt, content.markdown)
        self.assertNotIn("![Question image]", content.markdown)

    def test_image_markdown_uses_resolved_image_path_when_requested(self) -> None:
        image_dir = DEFAULT_CSV_PATH.parent / "images"
        test = self.service.get_test(self.service.list_tests()[0].id)
        image_question = next(
            question for question in test.questions if question.stimulus_type == "image"
        )

        markdown = format_question_markdown(
            image_question,
            image_asset_dir=image_dir,
        )

        self.assertIn(
            f"![Question image]({image_dir / image_question.stimulus})",
            markdown,
        )

    def test_missing_image_question_content_shows_fallback_text(self) -> None:
        test = self.service.get_test(self.service.list_tests()[0].id)
        image_question = next(
            question for question in test.questions if question.stimulus_type == "image"
        )

        content = format_question_content(
            image_question,
            image_asset_dir=Path(self._temp_dir.name),
        )

        self.assertIsNone(content.image_path)
        self.assertIn(
            f"Image stimulus unavailable: `{image_question.stimulus}`",
            content.markdown,
        )


if __name__ == "__main__":
    unittest.main()

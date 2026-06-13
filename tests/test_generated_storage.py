from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from harness import GenerationRequest
from services import create_quiz_service
from storage import DEFAULT_CSV_PATH
from tests.fake_chat_client import FakeChatClient


class GeneratedStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "quizcat.sqlite3"
        self.service = create_quiz_service(
            db_path=self.db_path, seed_csv_path=DEFAULT_CSV_PATH
        )

    def tearDown(self) -> None:
        self.service.close()
        self._temp_dir.cleanup()

    def _request(self, *types: str) -> GenerationRequest:
        return GenerationRequest(
            question_types=tuple(types), examples_per_type=3, max_attempts=2
        )

    def test_generated_test_lists_beside_seed_exams(self) -> None:
        result = self.service.generate_test(
            client=FakeChatClient(),
            request=self._request("Analogies", "Applied Quantitative Word Problems"),
        )
        self.assertTrue(result.succeeded)

        tests = self.service.list_tests()
        self.assertEqual(9, len(tests))  # 8 seed + 1 generated
        generated = [test for test in tests if test.kind == "generated"]
        self.assertEqual(1, len(generated))
        self.assertEqual("Generated Exam 1", generated[0].title)
        self.assertEqual(2, generated[0].question_count)

    def test_generated_questions_are_playable(self) -> None:
        result = self.service.generate_test(
            client=FakeChatClient(),
            request=self._request("Analogies", "Applied Quantitative Word Problems"),
        )
        definition = self.service.get_test(result.test_id)
        self.assertEqual(2, len(definition.questions))
        for question in definition.questions:
            self.assertEqual("generated", question.origin)
            # Correct answer resolves to a real choice — quiz scoring works.
            self.assertIsNotNone(
                question.choice_for_label(question.correct_choice_label)
            )

    def test_run_and_attempt_traces_persisted(self) -> None:
        self.service.generate_test(
            client=FakeChatClient(),
            request=self._request("Applied Quantitative Word Problems"),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            run = connection.execute("SELECT * FROM harness_runs").fetchone()
            self.assertEqual("completed", run["status"])
            self.assertEqual(1, run["accepted_count"])
            self.assertIsNotNone(run["test_id"])

            attempts = connection.execute(
                "SELECT * FROM harness_question_attempts WHERE run_id = ?",
                (run["id"],),
            ).fetchall()
            self.assertTrue(attempts)
            tool_calls = json.loads(attempts[-1]["tool_calls"])
            self.assertTrue(tool_calls)
            self.assertEqual("calculate", tool_calls[0]["tool_name"])

    def test_failed_run_records_trace_without_test(self) -> None:
        # Verifier never passes -> no question accepted -> no test created.
        result = self.service.generate_test(
            client=FakeChatClient(verdict_sequence=["fail", "fail", "fail", "fail"]),
            request=self._request("Applied Quantitative Word Problems"),
        )
        self.assertFalse(result.succeeded)
        self.assertIsNone(result.test_id)
        self.assertEqual("failed", result.summary.status)

        # Still 8 seed tests, but a run trace exists for observability.
        self.assertEqual(8, len(self.service.list_tests()))
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            run = connection.execute("SELECT * FROM harness_runs").fetchone()
            self.assertEqual("failed", run["status"])
            self.assertIsNone(run["test_id"])

    def test_seed_reimport_is_idempotent_after_generation(self) -> None:
        self.service.generate_test(
            client=FakeChatClient(), request=self._request("Analogies")
        )
        self.service.close()
        # Re-open the same DB: seed import must not duplicate the 8 exams,
        # and the generated test must survive.
        self.service = create_quiz_service(
            db_path=self.db_path, seed_csv_path=DEFAULT_CSV_PATH
        )
        tests = self.service.list_tests()
        self.assertEqual(8, sum(1 for t in tests if t.kind == "source_exam"))
        self.assertEqual(1, sum(1 for t in tests if t.kind == "generated"))


if __name__ == "__main__":
    unittest.main()

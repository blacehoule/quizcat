from __future__ import annotations

import unittest

import harness
from harness import (
    GeneratedQuestionDraft,
    GenerationRequest,
    draft_from_parsed,
    extract_json_candidate,
    parse_json_response_with_error,
    parse_standard_response,
    run_generation,
    safe_calculate_expression,
    validate_draft,
)
from models import Choice, Question
from tests.fake_chat_client import FakeChatClient


class FakeProvider:
    """In-memory :class:`harness.ExampleProvider` for harness loop tests."""

    TYPES = {
        "Analogies": "Verbal",
        "Applied Quantitative Word Problems": "Math & Logic",
        "Syllogisms / Formal Logic": "Math & Logic",
    }

    def available_question_types(self) -> list[str]:
        return sorted(self.TYPES)

    def examples_for_type(self, question_type: str, limit: int) -> list[Question]:
        category = self.TYPES[question_type]
        return [
            Question(
                id=index,
                external_id=None,
                origin="seed",
                source_exam=None,
                source_file=None,
                source_category=None,
                source_question_number=None,
                category=category,
                question_type=question_type,
                prompt="",
                stimulus=f"{question_type} example {index}",
                stimulus_type="text",
                correct_choice_label="A",
                correct_choice_text="x",
                explanation="because x",
                choices=(Choice("A", "x", 1), Choice("B", "y", 2)),
            )
            for index in range(1, min(limit, 2) + 1)
        ]

    def existing_stimuli_for_type(self, question_type: str) -> set[str]:
        return {f"{question_type} example 1"}


def _draft(**overrides) -> GeneratedQuestionDraft:
    base = dict(
        category="Verbal",
        question_type="Analogies",
        prompt="",
        stimulus="A is to B as C is to ?",
        stimulus_type="text",
        choices=(
            Choice("A", "one", 1),
            Choice("B", "two", 2),
            Choice("C", "three", 3),
            Choice("D", "four", 4),
            Choice("E", "five", 5),
        ),
        correct_choice_label="A",
        correct_choice_text="one",
        explanation="because one",
    )
    base.update(overrides)
    return GeneratedQuestionDraft(**base)


class CalculatorTests(unittest.TestCase):
    def test_arithmetic(self) -> None:
        self.assertEqual("18", safe_calculate_expression("4.50 * 4"))
        self.assertEqual("26220", safe_calculate_expression("57,000 * 46%"))
        self.assertEqual("3.33", safe_calculate_expression("round(10 / 3, 2)"))

    def test_rejects_unsafe(self) -> None:
        with self.assertRaises(ValueError):
            safe_calculate_expression("__import__('os').system('echo hi')")
        with self.assertRaises(ValueError):
            safe_calculate_expression("2 ** 50")

    def test_tool_wrapper_reports_errors(self) -> None:
        self.assertTrue(harness.calculate("nope(").startswith("ERROR"))


class ParsingTests(unittest.TestCase):
    def test_extract_json_from_fence_and_prose(self) -> None:
        self.assertEqual('{"a": 1}', extract_json_candidate('```json\n{"a": 1}\n```'))
        self.assertEqual('{"a": 1}', extract_json_candidate('text {"a": 1} tail'))
        self.assertIsNone(extract_json_candidate("no object here"))

    def test_parse_json_error_reporting(self) -> None:
        parsed, error = parse_json_response_with_error('{"a": 1}')
        self.assertEqual({"a": 1}, parsed)
        self.assertEqual("", error)
        parsed, error = parse_json_response_with_error("{not valid}")
        self.assertIsNone(parsed)
        self.assertIn("line", error)

    def test_parse_standard_format(self) -> None:
        text = (
            "QUESTION:\nWhat is X?\n\nCHOICES:\nA: one\nB: two\nC: three\n\n"
            "ANSWER:\nB\n\nEXPLANATION:\nbecause two"
        )
        parsed = parse_standard_response(text)
        self.assertEqual("B", parsed["answer"])
        self.assertEqual("two", parsed["choices"]["B"])

        draft = draft_from_parsed(parsed, category="Verbal", question_type="Analogies")
        self.assertEqual("two", draft.correct_choice_text)

    def test_parse_standard_returns_none_when_incomplete(self) -> None:
        self.assertIsNone(parse_standard_response("QUESTION:\nonly a question"))


class GuardrailTests(unittest.TestCase):
    valid_types = {"Analogies", "Applied Quantitative Word Problems"}

    def test_valid_draft_passes(self) -> None:
        errors = validate_draft(
            _draft(), valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertEqual([], errors)

    def test_unparseable_draft(self) -> None:
        errors = validate_draft(
            None, valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertEqual(1, len(errors))

    def test_wrong_choice_count(self) -> None:
        draft = _draft(choices=(Choice("A", "one", 1), Choice("B", "two", 2)))
        errors = validate_draft(
            draft, valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertTrue(any("3 or 5 choices" in error for error in errors))

    def test_correct_label_not_in_choices(self) -> None:
        draft = _draft(correct_choice_label="Z", correct_choice_text="one")
        errors = validate_draft(
            draft, valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertTrue(any("not among the choices" in error for error in errors))

    def test_correct_text_mismatch(self) -> None:
        draft = _draft(correct_choice_text="WRONG")
        errors = validate_draft(
            draft, valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertTrue(any("does not match" in error for error in errors))

    def test_invalid_taxonomy(self) -> None:
        draft = _draft(category="Nonsense", question_type="Nope")
        errors = validate_draft(
            draft, valid_question_types=self.valid_types, existing_stimuli=set()
        )
        self.assertTrue(any("category" in error for error in errors))
        self.assertTrue(any("question_type" in error for error in errors))

    def test_duplicate_stimulus(self) -> None:
        draft = _draft()
        errors = validate_draft(
            draft,
            valid_question_types=self.valid_types,
            existing_stimuli={"a is to b as c is to ?"},
        )
        self.assertTrue(any("duplicates" in error for error in errors))


class GenerationLoopTests(unittest.TestCase):
    def _request(self, *types: str) -> GenerationRequest:
        return GenerationRequest(
            question_types=tuple(types), examples_per_type=2, max_attempts=3
        )

    def test_standard_and_math_accepted(self) -> None:
        summary = run_generation(
            FakeChatClient(),
            FakeProvider(),
            self._request("Analogies", "Applied Quantitative Word Problems"),
        )
        self.assertEqual("completed", summary.status)
        self.assertEqual(2, summary.accepted_count)
        # The math question recorded calculator tool calls.
        math_trace = next(t for t in summary.traces if t.used_tool_path)
        self.assertTrue(math_trace.tool_calls)

    def test_math_retry_until_pass(self) -> None:
        client = FakeChatClient(verdict_sequence=["fail", "pass"])
        summary = run_generation(
            client, FakeProvider(), self._request("Applied Quantitative Word Problems")
        )
        self.assertEqual(1, summary.accepted_count)
        accepted_trace = summary.traces[-1]
        self.assertTrue(accepted_trace.accepted)
        self.assertEqual(2, accepted_trace.attempt_number)
        self.assertEqual(2, len(summary.traces))  # one rejected, one accepted

    def test_math_fails_after_max_attempts(self) -> None:
        client = FakeChatClient(verdict_sequence=["fail", "fail", "fail"])
        summary = run_generation(
            client, FakeProvider(), self._request("Applied Quantitative Word Problems")
        )
        self.assertEqual("failed", summary.status)
        self.assertEqual(0, summary.accepted_count)
        self.assertEqual(3, len(summary.traces))
        self.assertFalse(any(t.accepted for t in summary.traces))

    def test_json_repair_path(self) -> None:
        client = FakeChatClient(malformed_first_math=True)
        summary = run_generation(
            client, FakeProvider(), self._request("Applied Quantitative Word Problems")
        )
        self.assertEqual(1, summary.accepted_count)
        self.assertGreaterEqual(summary.traces[-1].json_repair_attempts, 1)

    def test_progress_callback_fires_per_question(self) -> None:
        events = []
        run_generation(
            FakeChatClient(),
            FakeProvider(),
            self._request("Analogies", "Syllogisms / Formal Logic"),
            on_question=events.append,
        )
        self.assertEqual([1, 2], [event.position for event in events])
        self.assertTrue(all(event.requested_count == 2 for event in events))


if __name__ == "__main__":
    unittest.main()

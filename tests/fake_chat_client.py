"""A scripted :class:`harness.ChatClient` for deterministic harness tests.

Routes by prompt content so a single fake can serve every leg of the loop:
standard generation, math generation, JSON repair, and verification. No
network or API key is involved.
"""

from __future__ import annotations

import json
import re

from harness import ToolCallRecord, ToolLoopResult

_RESOLVED_TYPE = re.compile(r"Requested question type:\s*\n(.+)")
_CALC = (ToolCallRecord(tool_name="calculate", args={"expression": "2 * 2"}, result="4"),)


class FakeChatClient:
    """Configurable fake.

    Parameters
    ----------
    verdict_sequence:
        Verdicts the verifier returns in order; falls back to ``pass`` once
        exhausted. Use ``["fail", "pass"]`` to exercise the retry loop.
    malformed_first_math:
        When true, the first math-generation call returns non-JSON to force
        the JSON-repair path.
    """

    def __init__(
        self,
        *,
        verdict_sequence: list[str] | None = None,
        malformed_first_math: bool = False,
    ) -> None:
        self.verdict_sequence = list(verdict_sequence or [])
        self.malformed_first_math = malformed_first_math
        self._stimulus_counter = 0
        self._math_gen_calls = 0
        self.completions = 0
        self.tool_loops = 0

    # -- ChatClient surface -------------------------------------------------

    def complete(self, prompt: str) -> str:
        self.completions += 1
        resolved = self._resolved_type(prompt)
        if "previously returned invalid JSON" in prompt:
            return self._math_json(resolved)
        return self._standard_text(resolved)

    def complete_with_tools(self, prompt: str, *, max_tool_rounds: int = 6) -> ToolLoopResult:
        self.tool_loops += 1
        resolved = self._resolved_type(prompt)
        if "strict verifier" in prompt:
            verdict = self.verdict_sequence.pop(0) if self.verdict_sequence else "pass"
            text = json.dumps({"verdict": verdict, "notes": f"verdict={verdict}"})
            return ToolLoopResult(text=text, tool_calls=_CALC)

        self._math_gen_calls += 1
        if self.malformed_first_math and self._math_gen_calls == 1:
            return ToolLoopResult(text="this is not json", tool_calls=_CALC)
        return ToolLoopResult(text=self._math_json(resolved), tool_calls=_CALC)

    # -- helpers ------------------------------------------------------------

    def _resolved_type(self, prompt: str) -> str:
        match = _RESOLVED_TYPE.search(prompt)
        return match.group(1).strip() if match else "Unknown"

    def _unique_stimulus(self, resolved: str) -> str:
        self._stimulus_counter += 1
        return f"{resolved} generated stimulus #{self._stimulus_counter}"

    def _standard_text(self, resolved: str) -> str:
        return (
            "QUESTION:\n"
            f"{self._unique_stimulus(resolved)}\n\n"
            "CHOICES:\n"
            "A: alpha\nB: beta\nC: gamma\nD: delta\nE: epsilon\n\n"
            "ANSWER:\nA\n\n"
            "EXPLANATION:\nBecause alpha is correct."
        )

    def _math_json(self, resolved: str) -> str:
        return json.dumps(
            {
                "question": self._unique_stimulus(resolved),
                "choices": {
                    "A": "$10.00",
                    "B": "$20.00",
                    "C": "$30.00",
                    "D": "$40.00",
                    "E": "$50.00",
                },
                "answer": "A",
                "explanation": "Ten dollars total.",
                "calculation_notes": ["5 * 2 -> 10"],
            }
        )

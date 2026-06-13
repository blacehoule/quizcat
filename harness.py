"""CCAT-style question-generation harness.

This module is the production-shaped descendant of ``Harness_Development.ipynb``.
The notebook drove generation off a pandas dataframe and printed results; here
the same loop reads its few-shot examples from the application's question store
and returns structured, persistable results so the Textual UI can play and
inspect generated tests.

The harness demonstrates four hackathon components directly in-product:

* **Main loop** — :func:`run_generation` walks a fixed question-type
  distribution, generating and validating one question per slot.
* **Tool calling** — math-like types route through a calculator-enabled
  generation and verification path (:class:`ChatClient.complete_with_tools`).
* **Guardrails** — :func:`validate_draft` rejects malformed questions, and the
  math verifier retries failed/warning verdicts up to ``max_attempts``.
* **Observability** — every attempt yields a :class:`HarnessQuestionTrace`, and
  the run yields a :class:`HarnessRunSummary`, both persisted by the caller.

Only the :class:`ChatClient` boundary touches the network. The calculator,
parsing, and guardrail logic are pure and unit-testable without an API key, and
tests inject a scripted client to exercise the loop deterministically.
"""

from __future__ import annotations

import ast
import json
import math
import operator
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from models import Choice, Question


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

VALID_CATEGORIES = frozenset({"Verbal", "Math & Logic", "Spatial Reasoning"})
VALID_STIMULUS_TYPES = frozenset({"text", "text_table", "image"})

# Math-like types route through the calculator + verifier path. Mirrors the
# notebook set; these are the types where a numeric answer can be checked.
MATH_LIKE_QUESTION_TYPES = frozenset(
    {
        "Applied Quantitative Word Problems",
        "Basic Numeric Calculation & Comparison",
        "Number Series",
        "Percent, Ratio & Proportion",
        "Tables & Graphs",
    }
)

# Older labels seen in earlier prompt work, mapped onto current taxonomy.
QUESTION_TYPE_ALIASES = {
    "Basic Arithmetic Word Problems": "Applied Quantitative Word Problems",
    "Exact Match Count": "Attention to Detail",
    "Letter Series": "Letter-Group Series",
    "Logic Statements": "Syllogisms / Formal Logic",
    "Logic Statements: True / False / Uncertain": "Syllogisms / Formal Logic",
    "Opposites": "Antonyms",
}

# Deterministic default 10-question distribution. Spans all three categories
# while staying text-renderable: math types exercise the tool path, Odd One Out
# is requested as a text-only equivalent of its image-based bank examples.
DEFAULT_DISTRIBUTION: tuple[str, ...] = (
    "Analogies",
    "Sentence Completion",
    "Antonyms",
    "Applied Quantitative Word Problems",
    "Percent, Ratio & Proportion",
    "Basic Numeric Calculation & Comparison",
    "Number Series",
    "Syllogisms / Formal Logic",
    "Arrangement Logic",
    "Odd One Out",
)


# ---------------------------------------------------------------------------
# Request / result data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationRequest:
    """Settings for one harness run."""

    question_types: tuple[str, ...] = DEFAULT_DISTRIBUTION
    examples_per_type: int = 6
    max_attempts: int = 3

    @property
    def requested_count(self) -> int:
        return len(self.question_types)


@dataclass(frozen=True)
class GeneratedQuestionDraft:
    """A structurally complete generated question, pre-persistence."""

    category: str
    question_type: str
    prompt: str
    stimulus: str
    stimulus_type: str
    choices: tuple[Choice, ...]
    correct_choice_label: str
    correct_choice_text: str
    explanation: str


@dataclass(frozen=True)
class ToolCallRecord:
    """One calculator invocation made by the model."""

    tool_name: str
    args: dict[str, Any]
    result: str

    def as_dict(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "args": self.args, "result": self.result}


@dataclass(frozen=True)
class ToolLoopResult:
    """The text a tool-enabled completion returned, plus its tool calls."""

    text: str
    tool_calls: tuple[ToolCallRecord, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    """Normalized math-verifier verdict."""

    verdict: str  # pass | warning | fail | not_applicable
    checked_expression: str = ""
    expected_answer: str = ""
    model_answer: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checked_expression": self.checked_expression,
            "expected_answer": self.expected_answer,
            "model_answer": self.model_answer,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HarnessQuestionTrace:
    """Full observability record for a single generation attempt."""

    requested_type: str
    resolved_type: str
    attempt_number: int
    used_tool_path: bool
    raw_model_output: str
    final_output: str
    json_repair_attempts: int
    tool_calls: tuple[ToolCallRecord, ...]
    verification: VerificationResult
    guardrail_errors: tuple[str, ...]
    accepted: bool
    draft: GeneratedQuestionDraft | None


@dataclass(frozen=True)
class ProgressEvent:
    """Live progress emitted after each requested question is resolved."""

    position: int
    requested_count: int
    requested_type: str
    resolved_type: str
    accepted: bool
    verdict: str
    attempts_used: int
    accepted_count: int


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class HarnessRunSummary:
    """Outcome of a full :func:`run_generation` call."""

    request: GenerationRequest
    accepted: tuple[GeneratedQuestionDraft, ...]
    traces: tuple[HarnessQuestionTrace, ...]
    status: str  # completed | partial | failed
    error: str = ""

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)


# ---------------------------------------------------------------------------
# Calculator tool (pure, no network)
# ---------------------------------------------------------------------------

_SAFE_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SAFE_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_SAFE_FUNCTIONS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "sqrt": math.sqrt,
}
_SAFE_NAMES = {
    "e": math.e,
    "pi": math.pi,
}


def normalize_calculator_expression(expression: str) -> str:
    """Strip currency/grouping symbols and turn ``46%`` into ``(46 / 100)``."""
    expression = str(expression).strip()
    expression = expression.replace("$", "")
    expression = re.sub(r"(?<=\d),(?=\d{3}(\D|$))", "", expression)
    expression = re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*%(?!\s*\d)",
        r"(\1 / 100)",
        expression,
    )
    return expression


def _evaluate_safe_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate_safe_ast(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric constants are allowed")
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in _SAFE_NAMES:
            raise ValueError(f"Unknown name: {node.id}")
        return _SAFE_NAMES[node.id]

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)
        if operator_type not in _SAFE_BINARY_OPERATORS:
            raise ValueError(f"Unsupported operator: {operator_type.__name__}")
        left = _evaluate_safe_ast(node.left)
        right = _evaluate_safe_ast(node.right)
        if operator_type is ast.Pow and abs(right) > 10:
            raise ValueError("Exponents greater than 10 are not allowed")
        return _SAFE_BINARY_OPERATORS[operator_type](left, right)

    if isinstance(node, ast.UnaryOp):
        operator_type = type(node.op)
        if operator_type not in _SAFE_UNARY_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {operator_type.__name__}")
        return _SAFE_UNARY_OPERATORS[operator_type](_evaluate_safe_ast(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
            raise ValueError("Only allowlisted math functions can be called")
        if node.keywords:
            raise ValueError("Keyword arguments are not supported")
        if len(node.args) > 2:
            raise ValueError("Calculator functions accept at most two arguments")
        args = [_evaluate_safe_ast(arg) for arg in node.args]
        return _SAFE_FUNCTIONS[node.func.id](*args)

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def _format_calculator_result(result: float) -> str:
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("Result is not finite")
    if abs(result - round(result)) < 1e-12:
        return str(int(round(result)))
    return format(result, ".12g")


def safe_calculate_expression(expression: str) -> str:
    """Evaluate an arithmetic expression, rejecting anything non-arithmetic."""
    normalized_expression = normalize_calculator_expression(expression)
    if not normalized_expression:
        raise ValueError("Expression is empty")
    if len(normalized_expression) > 240:
        raise ValueError("Expression is too long")

    parsed_expression = ast.parse(normalized_expression, mode="eval")
    result = _evaluate_safe_ast(parsed_expression)
    return _format_calculator_result(result)


def calculate(expression: str) -> str:
    """Tool entry point: never raises, reports errors back to the model."""
    try:
        return safe_calculate_expression(expression)
    except Exception as exc:  # noqa: BLE001 - errors are fed back to the model
        return f"ERROR: {exc}"


def is_math_like_question_type(question_type: str) -> bool:
    return question_type in MATH_LIKE_QUESTION_TYPES


# ---------------------------------------------------------------------------
# Prompts (placeholders substituted with str.replace, not str.format, so the
# literal JSON braces in the math prompts need no escaping)
# ---------------------------------------------------------------------------

GENERATION_PROMPT_TEMPLATE = """
You are a CCAT-style question-generation assistant.

Your task is to generate one new multiple-choice question that belongs to the requested question type.

Use the corpus to learn the style, difficulty, structure, answer-choice format, and reasoning pattern for the requested question type.

Do not copy, lightly paraphrase, or reuse any existing question from the corpus. Generate a genuinely new question that could plausibly belong in the same dataset.

Requested question type:
{QUESTION_TYPE}

Corpus of labeled example questions:
{LABELED_QUESTION_CORPUS}

Question-type rules:
- If the corpus examples use exactly three choices, generate exactly three choices labeled A, B, and C.
- Otherwise, generate exactly five choices labeled A, B, C, D, and E.
- If the examples are image-stimulus questions, do not invent an image filename. Generate a text-only version that preserves the reasoning pattern.

General requirements:
- Generate exactly one question.
- The question must clearly fit the requested question type.
- Include exactly one correct answer.
- Make all incorrect choices plausible but clearly wrong.
- Match the style and approximate difficulty of the corpus examples.
- Avoid ambiguity and outside knowledge.
- Do not mention the corpus. Do not explain that the question is new.

Return your answer in exactly this format:

QUESTION:
[question text]

CHOICES:
A: [choice A]
B: [choice B]
C: [choice C]
[include D and E only when the question uses five choices]

ANSWER:
[correct choice letter]

EXPLANATION:
[brief explanation of why the correct choice is correct and why the other choices are not]
"""

MATH_GENERATION_PROMPT_TEMPLATE = """
You are a CCAT-style math question-generation assistant with access to a calculator tool named calculate.

Your task is to generate one new multiple-choice question that belongs to the requested math-like question type.

Requested question type:
{QUESTION_TYPE}

Corpus of labeled example questions:
{LABELED_QUESTION_CORPUS}

Use the corpus to learn the style, difficulty, structure, answer-choice format, and reasoning pattern for the requested question type.

Calculator requirements:
- Use the calculate tool for every non-trivial arithmetic step before choosing the correct answer.
- Do not guess arithmetic mentally when a calculation is needed.
- Put the expressions you checked in calculation_notes.
- Return valid JSON. Every displayed answer choice value must be a JSON string in double quotes, especially numbers with commas, currency, or units such as 18,000, $18.00, or 46%.

Question requirements:
- Generate exactly one question.
- Include exactly one correct answer.
- Make all incorrect choices plausible but clearly wrong.
- Match the style and approximate difficulty of the corpus examples.
- Avoid ambiguity and outside knowledge.
- Do not mention the corpus or the calculator.

Return JSON only, with this exact shape:
{
  "question": "[question text]",
  "choices": {
    "A": "[choice A]",
    "B": "[choice B]",
    "C": "[choice C]",
    "D": "[choice D]",
    "E": "[choice E]"
  },
  "answer": "[correct choice letter]",
  "explanation": "[brief explanation of why the correct choice is correct and why the other choices are not]",
  "calculation_notes": ["[calculator expression checked -> result]"]
}
"""

MATH_VERIFICATION_PROMPT_TEMPLATE = """
You are a strict verifier for generated CCAT-style math questions. You have access to a calculator tool named calculate.

Requested question type:
{QUESTION_TYPE}

Generated question JSON:
{GENERATED_OUTPUT_JSON}

Verification task:
- Check whether the listed correct answer follows from the numbers in the generated question.
- Use the calculate tool for arithmetic checks.
- If the question cannot be fully checked from the provided text, return warning rather than pass.
- If the answer is numerically wrong, return fail.

Return JSON only, with this exact shape:
{
  "verdict": "pass | warning | fail",
  "checked_expression": "[main calculator expression checked, or blank]",
  "expected_answer": "[numeric/text answer you verified, or blank]",
  "model_answer": "[answer choice and value from the generated question, or blank]",
  "notes": "[short explanation of the verdict]"
}
"""

MATH_JSON_REPAIR_PROMPT_TEMPLATE = """
You previously returned invalid JSON for a generated math question.

Requested question type:
{QUESTION_TYPE}

JSON parser error:
{PARSE_ERROR}

Invalid response:
{INVALID_RESPONSE}

Fix the response so it is valid JSON only.

Rules:
- Do not wrap the JSON in markdown fences.
- Do not add commentary before or after the JSON.
- Preserve the generated question, choices, answer, explanation, and calculation_notes unless a minimal syntax fix is required.
- Every displayed answer choice value must be a JSON string in double quotes.
- Numbers with commas, currency symbols, percentages, or units must be strings, not bare JSON numbers.
- The output must parse with json.loads.
"""


def _render_prompt(template: str, **values: str) -> str:
    rendered = template.strip()
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


# ---------------------------------------------------------------------------
# Chat client boundary
# ---------------------------------------------------------------------------


class ChatClient(Protocol):
    """The only network-touching surface of the harness."""

    def complete(self, prompt: str) -> str:
        """Return the model's text for a plain (toolless) completion."""

    def complete_with_tools(
        self, prompt: str, *, max_tool_rounds: int = 6
    ) -> ToolLoopResult:
        """Run a calculator-enabled tool loop and return text plus tool calls."""


class LangChainChatClient:
    """OpenAI-backed :class:`ChatClient` using LangChain, as in the notebook."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> None:
        # Imported lazily so the rest of the harness (calculator, parsing,
        # guardrails, the whole loop under a fake client) imports without
        # langchain or an API key present.
        from langchain_core.messages import HumanMessage, ToolMessage
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI

        self._HumanMessage = HumanMessage
        self._ToolMessage = ToolMessage

        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if temperature is None:
            temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

        self._llm = ChatOpenAI(model=model, temperature=temperature)

        @tool
        def calculate_tool(expression: str) -> str:
            """Evaluate a safe arithmetic expression. Use this for numeric
            checks; write percentages as 46% or 46 / 100."""
            return calculate(expression)

        self._tool = calculate_tool
        self._llm_with_tools = self._llm.bind_tools([calculate_tool])

    def complete(self, prompt: str) -> str:
        message = self._llm.invoke([self._HumanMessage(content=prompt)])
        return _message_content_to_text(message.content)

    def complete_with_tools(
        self, prompt: str, *, max_tool_rounds: int = 6
    ) -> ToolLoopResult:
        messages = [self._HumanMessage(content=prompt)]
        tool_records: list[ToolCallRecord] = []

        for _ in range(max_tool_rounds):
            ai_message = self._llm_with_tools.invoke(messages)
            messages.append(ai_message)
            tool_calls = getattr(ai_message, "tool_calls", None) or []

            if not tool_calls:
                text = _message_content_to_text(ai_message.content)
                return ToolLoopResult(text=text, tool_calls=tuple(tool_records))

            for tool_call in tool_calls:
                tool_args = tool_call.get("args", {})
                if tool_call.get("name") == self._tool.name:
                    result = self._tool.invoke(tool_args)
                else:
                    result = f"ERROR: Unknown tool {tool_call.get('name')}"
                tool_records.append(
                    ToolCallRecord(
                        tool_name=str(tool_call.get("name")),
                        args=dict(tool_args),
                        result=str(result),
                    )
                )
                messages.append(
                    self._ToolMessage(
                        content=str(result), tool_call_id=tool_call.get("id")
                    )
                )

        raise RuntimeError(f"Tool loop exceeded {max_tool_rounds} rounds")


def create_chat_client(
    *, model: str | None = None, temperature: float | None = None
) -> ChatClient:
    """Build the default OpenAI-backed client, loading ``.env`` if present."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env or the environment to "
            "generate questions."
        )
    return LangChainChatClient(model=model, temperature=temperature)


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Example corpus from stored questions
# ---------------------------------------------------------------------------


class ExampleProvider(Protocol):
    """Supplies few-shot examples and taxonomy from the question store."""

    def available_question_types(self) -> list[str]:
        ...

    def examples_for_type(self, question_type: str, limit: int) -> list[Question]:
        ...

    def existing_stimuli_for_type(self, question_type: str) -> set[str]:
        ...


def resolve_question_type(requested_type: str, available_types: Sequence[str]) -> str:
    """Resolve exact names, known aliases, and unambiguous partial matches."""
    requested_type = requested_type.strip()
    if requested_type in QUESTION_TYPE_ALIASES:
        requested_type = QUESTION_TYPE_ALIASES[requested_type]

    normalized = {qt.casefold(): qt for qt in available_types}
    if requested_type.casefold() in normalized:
        return normalized[requested_type.casefold()]

    partial = [qt for qt in available_types if requested_type.casefold() in qt.casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise ValueError(
            f"Ambiguous question type {requested_type!r}. Matches: {partial}"
        )
    raise ValueError(
        f"Unknown question type {requested_type!r}. "
        f"Available types: {sorted(available_types)}"
    )


def _format_example_stimulus(question: Question) -> str:
    stimulus = question.stimulus.strip()
    if not stimulus:
        return ""
    if question.stimulus_type == "image":
        return f"IMAGE STIMULUS: {stimulus}"
    if question.stimulus_type == "text_table":
        return _format_text_table(stimulus)
    return stimulus


def _format_text_table(stimulus: str) -> str:
    rows: list[list[str]] = []
    for raw_row in stimulus.split(";"):
        cells = [cell.strip() for cell in raw_row.split("|")]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(cells) for cells in rows)
    rows = [cells + [""] * (width - len(cells)) for cells in rows]
    widths = [max(len(row[i]) for row in rows) for i in range(width)]
    separator = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    lines = [separator]
    for row in rows:
        lines.append(
            "| " + " | ".join(f"{row[i]:<{widths[i]}}" for i in range(width)) + " |"
        )
        lines.append(separator)
    return "\n".join(lines)


def _format_example(question: Question) -> str:
    parts = [f"QUESTION TYPE: {question.question_type}"]
    if question.prompt.strip():
        parts.extend(["", question.prompt.strip()])
    stimulus = _format_example_stimulus(question)
    if stimulus:
        parts.extend(["", stimulus])
    choice_lines = [
        f"{choice.label}: {choice.text.strip()}"
        for choice in question.choices
        if choice.text.strip()
    ]
    if choice_lines:
        parts.extend(["", "\n".join(choice_lines)])
    parts.extend(
        [
            "",
            "CORRECT CHOICE:",
            question.correct_choice_label.strip(),
            "",
            "EXPLANATION:",
            question.explanation.strip(),
        ]
    )
    return "\n".join(parts)


def build_labeled_question_corpus(examples: Sequence[Question]) -> str:
    separator = "\n\n" + "=" * 100 + "\n\n"
    return separator.join(_format_example(question) for question in examples)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def extract_json_candidate(text: str) -> str | None:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


def parse_json_response_with_error(text: str) -> tuple[dict[str, Any] | None, str]:
    candidate = extract_json_candidate(text)
    if candidate is None:
        return None, "No JSON object found in model response."
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
    if not isinstance(parsed, dict):
        return None, "JSON parsed successfully but was not an object."
    return parsed, ""


_CHOICE_LINE = re.compile(r"^\s*([A-E])\s*[:.\)]\s*(.*\S)\s*$")
_SECTION_HEADERS = ("QUESTION", "CHOICES", "ANSWER", "EXPLANATION")


def parse_standard_response(text: str) -> dict[str, Any] | None:
    """Parse the ``QUESTION/CHOICES/ANSWER/EXPLANATION`` text format."""
    sections: dict[str, list[str]] = {header: [] for header in _SECTION_HEADERS}
    current: str | None = None
    for line in text.splitlines():
        header = line.strip().rstrip(":").upper()
        if header in _SECTION_HEADERS and line.strip().endswith(":"):
            current = header
            continue
        if current is not None:
            sections[current].append(line)

    question = "\n".join(sections["QUESTION"]).strip()
    explanation = "\n".join(sections["EXPLANATION"]).strip()
    answer = "\n".join(sections["ANSWER"]).strip().upper()
    answer = answer[:1] if answer else ""

    choices: dict[str, str] = {}
    for line in sections["CHOICES"]:
        match = _CHOICE_LINE.match(line)
        if match:
            choices[match.group(1).upper()] = match.group(2).strip()

    if not question or not choices or not answer:
        return None
    return {"question": question, "choices": choices, "answer": answer,
            "explanation": explanation}


def _coerce_choices(raw: Any) -> dict[str, str]:
    if isinstance(raw, list):
        return {chr(65 + i): str(value) for i, value in enumerate(raw)}
    if isinstance(raw, dict):
        return {str(label).upper(): str(value) for label, value in raw.items()}
    return {}


def draft_from_parsed(
    parsed: dict[str, Any] | None,
    *,
    category: str,
    question_type: str,
) -> GeneratedQuestionDraft | None:
    """Build a draft from a parsed generation payload, or ``None`` if unusable."""
    if not parsed:
        return None

    question = str(parsed.get("question", "")).strip()
    explanation = str(parsed.get("explanation", "")).strip()
    answer = str(parsed.get("answer", "")).strip().upper()[:1]
    raw_choices = _coerce_choices(parsed.get("choices", {}))

    choices: list[Choice] = []
    for position, label in enumerate(("A", "B", "C", "D", "E"), start=1):
        text = raw_choices.get(label, "").strip()
        if text:
            choices.append(Choice(label=label, text=text, position=position))

    correct_text = raw_choices.get(answer, "").strip()
    return GeneratedQuestionDraft(
        category=category,
        question_type=question_type,
        prompt="",
        stimulus=question,
        stimulus_type="text",
        choices=tuple(choices),
        correct_choice_label=answer,
        correct_choice_text=correct_text,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def validate_draft(
    draft: GeneratedQuestionDraft | None,
    *,
    valid_question_types: set[str],
    existing_stimuli: set[str],
) -> list[str]:
    """Return a list of guardrail violations; empty means the draft is valid."""
    if draft is None:
        return ["draft could not be parsed from the model output"]

    errors: list[str] = []
    if draft.category not in VALID_CATEGORIES:
        errors.append(f"category {draft.category!r} is not in the taxonomy")
    if draft.question_type not in valid_question_types:
        errors.append(f"question_type {draft.question_type!r} is not in the taxonomy")
    if draft.stimulus_type not in VALID_STIMULUS_TYPES:
        errors.append(f"stimulus_type {draft.stimulus_type!r} is invalid")
    if not draft.prompt.strip() and not draft.stimulus.strip():
        errors.append("prompt or stimulus is required")

    non_empty = [choice for choice in draft.choices if choice.text.strip()]
    if len(non_empty) not in (3, 5):
        errors.append(f"expected 3 or 5 choices, found {len(non_empty)}")

    labels = {choice.label.upper(): choice for choice in draft.choices}
    if not draft.correct_choice_label:
        errors.append("correct choice label is missing")
    elif draft.correct_choice_label.upper() not in labels:
        errors.append(
            f"correct label {draft.correct_choice_label!r} is not among the choices"
        )
    else:
        labeled = labels[draft.correct_choice_label.upper()]
        if labeled.text.strip() != draft.correct_choice_text.strip():
            errors.append("correct_choice_text does not match the labeled choice")

    if draft.stimulus.strip().casefold() in {
        stimulus.strip().casefold() for stimulus in existing_stimuli
    }:
        errors.append("stimulus duplicates an existing question of this type")

    return errors


# ---------------------------------------------------------------------------
# Generation paths
# ---------------------------------------------------------------------------


def _verdict_from_text(text: str) -> VerificationResult:
    parsed, _ = parse_json_response_with_error(text)
    if not parsed:
        return VerificationResult(
            verdict="warning",
            notes=f"Verifier did not return parseable JSON: {text[:200]}",
        )
    verdict = str(parsed.get("verdict", "warning")).strip().lower()
    notes = str(parsed.get("notes", "")).strip()
    if verdict not in {"pass", "warning", "fail", "not_applicable"}:
        notes = f"Verifier returned an unrecognized verdict ({verdict!r}). {notes}".strip()
        verdict = "warning"
    return VerificationResult(
        verdict=verdict,
        checked_expression=str(parsed.get("checked_expression", "")).strip(),
        expected_answer=str(parsed.get("expected_answer", "")).strip(),
        model_answer=str(parsed.get("model_answer", "")).strip(),
        notes=notes,
    )


@dataclass
class _AttemptOutcome:
    used_tool_path: bool
    raw_output: str
    final_output: str
    json_repair_attempts: int
    tool_calls: list[ToolCallRecord]
    verification: VerificationResult
    parsed: dict[str, Any] | None


def _generate_standard(client: ChatClient, resolved_type: str, corpus: str) -> _AttemptOutcome:
    prompt = _render_prompt(
        GENERATION_PROMPT_TEMPLATE,
        QUESTION_TYPE=resolved_type,
        LABELED_QUESTION_CORPUS=corpus,
    )
    text = client.complete(prompt)
    return _AttemptOutcome(
        used_tool_path=False,
        raw_output=text,
        final_output=text,
        json_repair_attempts=0,
        tool_calls=[],
        verification=VerificationResult(
            verdict="not_applicable",
            notes="Non-math question type skipped calculator verification.",
        ),
        parsed=parse_standard_response(text),
    )


def _repair_math_json(
    client: ChatClient, resolved_type: str, invalid_response: str, parse_error: str,
    max_repair_attempts: int = 2,
) -> tuple[dict[str, Any] | None, str, int]:
    response = invalid_response
    error = parse_error
    for attempt in range(1, max_repair_attempts + 1):
        prompt = _render_prompt(
            MATH_JSON_REPAIR_PROMPT_TEMPLATE,
            QUESTION_TYPE=resolved_type,
            PARSE_ERROR=error,
            INVALID_RESPONSE=response,
        )
        repaired = client.complete(prompt)
        parsed, error = parse_json_response_with_error(repaired)
        if parsed is not None:
            return parsed, repaired, attempt
        response = repaired
    return None, response, max_repair_attempts


def _generate_math(client: ChatClient, resolved_type: str, corpus: str) -> _AttemptOutcome:
    prompt = _render_prompt(
        MATH_GENERATION_PROMPT_TEMPLATE,
        QUESTION_TYPE=resolved_type,
        LABELED_QUESTION_CORPUS=corpus,
    )
    loop = client.complete_with_tools(prompt)
    tool_calls = list(loop.tool_calls)
    parsed, parse_error = parse_json_response_with_error(loop.text)
    final_output = loop.text
    repair_attempts = 0

    if parsed is None:
        parsed, final_output, repair_attempts = _repair_math_json(
            client, resolved_type, loop.text, parse_error
        )

    if parsed is None:
        verification = VerificationResult(
            verdict="warning",
            notes="Generated math response was not parseable JSON after repair; "
            "verification skipped.",
        )
    else:
        verification_prompt = _render_prompt(
            MATH_VERIFICATION_PROMPT_TEMPLATE,
            QUESTION_TYPE=resolved_type,
            GENERATED_OUTPUT_JSON=json.dumps(parsed, ensure_ascii=False, indent=2),
        )
        verify_loop = client.complete_with_tools(verification_prompt)
        tool_calls.extend(verify_loop.tool_calls)
        verification = _verdict_from_text(verify_loop.text)

    return _AttemptOutcome(
        used_tool_path=True,
        raw_output=loop.text,
        final_output=final_output,
        json_repair_attempts=repair_attempts,
        tool_calls=tool_calls,
        verification=verification,
        parsed=parsed,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def generate_one_question(
    client: ChatClient,
    provider: ExampleProvider,
    requested_type: str,
    *,
    examples_per_type: int,
    max_attempts: int,
    available_types: Sequence[str],
    valid_types: set[str],
    accepted_stimuli: set[str],
) -> list[HarnessQuestionTrace]:
    """Generate and validate one question, retrying on failure.

    Returns the trace for every attempt. The last trace is ``accepted`` iff a
    valid (and, for math types, verifier-passing) question was produced.
    """
    resolved_type = resolve_question_type(requested_type, available_types)
    examples = provider.examples_for_type(resolved_type, examples_per_type)
    if not examples:
        raise ValueError(f"No examples found for question type: {resolved_type}")
    category = examples[0].category
    corpus = build_labeled_question_corpus(examples)
    existing_stimuli = provider.existing_stimuli_for_type(resolved_type) | accepted_stimuli
    math_like = is_math_like_question_type(resolved_type)

    traces: list[HarnessQuestionTrace] = []
    for attempt in range(1, max_attempts + 1):
        if math_like:
            outcome = _generate_math(client, resolved_type, corpus)
        else:
            outcome = _generate_standard(client, resolved_type, corpus)

        draft = draft_from_parsed(
            outcome.parsed, category=category, question_type=resolved_type
        )
        guardrail_errors = validate_draft(
            draft,
            valid_question_types=valid_types,
            existing_stimuli=existing_stimuli,
        )
        verifier_ok = (not math_like) or outcome.verification.verdict == "pass"
        accepted = not guardrail_errors and verifier_ok

        traces.append(
            HarnessQuestionTrace(
                requested_type=requested_type,
                resolved_type=resolved_type,
                attempt_number=attempt,
                used_tool_path=outcome.used_tool_path,
                raw_model_output=outcome.raw_output,
                final_output=outcome.final_output,
                json_repair_attempts=outcome.json_repair_attempts,
                tool_calls=tuple(outcome.tool_calls),
                verification=outcome.verification,
                guardrail_errors=tuple(guardrail_errors),
                accepted=accepted,
                draft=draft,
            )
        )
        if accepted:
            break

    return traces


def run_generation(
    client: ChatClient,
    provider: ExampleProvider,
    request: GenerationRequest = GenerationRequest(),
    *,
    on_question: ProgressCallback | None = None,
) -> HarnessRunSummary:
    """Run the full generation loop over the requested type distribution.

    ``on_question`` is invoked once per requested type with a
    :class:`ProgressEvent`, letting the UI render live progress.
    """
    available_types = provider.available_question_types()
    valid_types = set(available_types)

    accepted: list[GeneratedQuestionDraft] = []
    accepted_stimuli: set[str] = set()
    all_traces: list[HarnessQuestionTrace] = []
    error = ""

    for position, requested_type in enumerate(request.question_types, start=1):
        try:
            traces = generate_one_question(
                client,
                provider,
                requested_type,
                examples_per_type=request.examples_per_type,
                max_attempts=request.max_attempts,
                available_types=available_types,
                valid_types=valid_types,
                accepted_stimuli=accepted_stimuli,
            )
        except Exception as exc:  # noqa: BLE001 - surface as a trace, keep going
            final = HarnessQuestionTrace(
                requested_type=requested_type,
                resolved_type=requested_type,
                attempt_number=0,
                used_tool_path=False,
                raw_model_output="",
                final_output="",
                json_repair_attempts=0,
                tool_calls=(),
                verification=VerificationResult(verdict="fail", notes=str(exc)),
                guardrail_errors=(str(exc),),
                accepted=False,
                draft=None,
            )
            all_traces.append(final)
            error = str(exc)
        else:
            all_traces.extend(traces)
            final = traces[-1]
            if final.accepted and final.draft is not None:
                accepted.append(final.draft)
                accepted_stimuli.add(final.draft.stimulus)

        if on_question is not None:
            on_question(
                ProgressEvent(
                    position=position,
                    requested_count=request.requested_count,
                    requested_type=requested_type,
                    resolved_type=final.resolved_type,
                    accepted=final.accepted,
                    verdict=final.verification.verdict,
                    attempts_used=final.attempt_number,
                    accepted_count=len(accepted),
                )
            )

    if not accepted:
        status = "failed"
    elif len(accepted) < request.requested_count:
        status = "partial"
    else:
        status = "completed"

    return HarnessRunSummary(
        request=request,
        accepted=tuple(accepted),
        traces=tuple(all_traces),
        status=status,
        error=error,
    )

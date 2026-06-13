import type { Question, QuestionContent } from "./types";

/**
 * Port of services.py's format_question_content / _format_text_table /
 * _markdown_table / _blockquote.
 *
 * Image stimuli are NOT embedded as markdown images here (unlike the TUI's
 * `include_image_markdown` path) — the web UI renders `imagePath` as a
 * separate <img>, mirroring QuestionImageDisplay.
 */
export function formatQuestionContent(
  question: Pick<Question, "prompt" | "stimulus" | "stimulusType" | "questionType">
): QuestionContent {
  const parts: string[] = [];

  if (question.prompt.trim()) {
    parts.push(blockquote(question.prompt.trim()));
  }

  switch (question.stimulusType) {
    case "image":
      return {
        markdown: joinMarkdownParts(parts),
        imagePath: `/images/${question.stimulus}`,
      };
    case "text_table":
      parts.push(formatTextTable(question));
      break;
    default:
      parts.push(question.stimulus);
      break;
  }

  return { markdown: joinMarkdownParts(parts), imagePath: null };
}

function blockquote(text: string): string {
  return text
    .split("\n")
    .map((line) => (line ? `> ${line}` : ">"))
    .join("\n");
}

function joinMarkdownParts(parts: string[]): string {
  return parts.filter((part) => part.trim()).join("\n\n");
}

function formatTextTable(
  question: Pick<Question, "stimulus" | "questionType">
): string {
  const rows = parseTextTableRows(question.stimulus);
  if (rows.length === 0) {
    return question.stimulus;
  }

  if (question.questionType === "Attention to Detail") {
    const width = Math.max(...rows.map((row) => row.length));
    return markdownTable(new Array(width).fill(""), rows);
  }

  const [header, ...body] = rows;
  if (body.length > 0 && body.every((row) => row.length === header.length)) {
    return markdownTable(header, body);
  }

  const width = Math.max(...rows.map((row) => row.length));
  return markdownTable(new Array(width).fill(""), rows);
}

function parseTextTableRows(stimulus: string): string[][] {
  return stimulus
    .split(";")
    .filter((row) => row.trim())
    .map((row) => row.split("|").map((cell) => escapeTableCell(cell.trim())));
}

function markdownTable(header: string[], rows: string[][]): string {
  const width = header.length;
  const lines = [
    markdownTableRow(padCells(header, width)),
    markdownTableRow(new Array(width).fill("---")),
    ...rows.map((row) => markdownTableRow(padCells(row, width))),
  ];
  return lines.join("\n");
}

function markdownTableRow(cells: string[]): string {
  return `| ${cells.join(" | ")} |`;
}

function padCells(cells: string[], width: number): string[] {
  const truncated = cells.slice(0, width);
  while (truncated.length < width) {
    truncated.push("");
  }
  return truncated;
}

function escapeTableCell(cell: string): string {
  return cell.replace(/\|/g, "\\|");
}

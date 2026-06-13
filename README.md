# QuizCat Terminal User Interface

## Live applications

- Full Next.js web app: https://quizcat-web-production.up.railway.app
- Textual browser app: https://quizcat-textual-production.up.railway.app

## Serve in a browser

Install dependencies and start the Textual web server:

```bash
uv sync
uv run python serve.py
```

Open `http://localhost:8000`.

### Deploy to Railway

The included `railway.toml` starts `python serve.py`. The server listens on
Railway's injected `PORT` environment variable and binds to `0.0.0.0`.

```bash
railway login
railway up
railway domain
```

`railway up` creates or selects a project and deploys the current directory.
`railway domain` generates the public Railway URL after the deployment is
healthy.

## Full Next.js web application

The production-style web application lives in `web/`. It uses the shared
question bank and a Postgres database, and can be deployed as a separate
Railway service without replacing the Textual browser service.

See `web/README.md` for local setup, database migration and seeding, and
deployment instructions.

## CCAT Question Bank Dataset Context

This project includes a seed dataset named `ccat_full_question_bank_prompt_stimulus.csv`. It contains 400 CCAT-style practice questions extracted from 8 BoostPrep Course Statistics reports, with 50 questions per source exam.

Each row represents one question. The dataset is intended to seed the application database, not to be treated as final production content. Preserve the data carefully during imports and migrations.

### Core structure

Questions are split into two conceptual fields:

* `prompt`: Reusable instructional text that explains how the question should be answered. This is often shared by many questions of the same type.
* `stimulus`: The unique content for the specific question. This is what the user must reason about to produce an answer.

Examples:

* Sentence completion:

  * `prompt`: “Choose the word or words that, when inserted in the sentence to replace the blank or blanks, best fits the meaning of the sentence.”
  * `stimulus`: The actual sentence with missing word(s).
* Antonym questions:

  * `prompt`: The instruction text asking for the opposite meaning.
  * `stimulus`: The all-caps target word.
* Attention to detail:

  * `prompt`: The shared instruction asking the user to compare entries.
  * `stimulus`: The five string pairs that would populate the comparison table.
* Image-based questions:

  * `prompt`: The text instruction for the question.
  * `stimulus`: The image filename needed to recover/render the image later.

### Stimulus types

The `stimulus_type` column indicates how the stimulus should be rendered:

* `text`: Plain text stimulus.
* `text_table`: Structured text that should eventually be rendered as a table, especially attention-to-detail questions.
* `image`: The stimulus is an image filename. The actual image asset may need to be resolved separately.

### Taxonomy

Each question has a broad `category` and a more specific `question_type`.

Primary categories:

* `Verbal`
* `Math & Logic`
* `Spatial Reasoning`

Primary question types include:

* Sentence Completion
* Analogies
* Attention to Detail
* Antonyms
* Applied Quantitative Word Problems
* Percent, Ratio & Proportion
* Syllogisms / Formal Logic
* Basic Numeric Calculation & Comparison
* Tables & Graphs
* Letter-Group Series
* Number Series
* Arrangement Logic
* Visual Next-in-Series
* Odd One Out
* Matrix Completion

Small one-off variants were intentionally rolled up into broader question types. For example, different numeric sequence patterns are all classified as `Number Series`, and different analogy relation types are all classified as `Analogies`.

### Answer fields

The dataset includes multiple-choice answer fields, a correct choice label, correct choice text, and an explanation. Import logic should preserve both the label and text because answer choice ordering matters for quiz rendering.

### Implementation notes for agents

When writing importers, seed scripts, migrations, or validation logic:

* Treat each CSV row as one question record.
* Do not recombine `prompt` and `stimulus`; they are intentionally separate.
* Preserve image filenames exactly as written in `stimulus`.
* Do not discard image-based questions.
* Do not assume every question has the same number of answer choices.
* Preserve explanations as plain text.
* Use `category`, `question_type`, and `stimulus_type` as controlled values where practical.
* Retain information about which exam the questions originated from
* Add validation that every imported question has a prompt or stimulus, at least one answer choice, a correct answer, a category, and a question type.
* Be careful with commas, quotes, and newlines when parsing the CSV; use a real CSV parser instead of string splitting.

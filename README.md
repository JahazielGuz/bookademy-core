# bookademy-core

Django + DRF + Postgres. Accounts, PDF uploads, the generated curriculum, and learner
progress. The system of record: everything the AI service produces is stored here.

## Apps

| App | Owns |
|---|---|
| `accounts` | The user model. Email is the login; Argon2id hashes the passwords. |
| `documents` | The uploaded PDF and the state of the generation run over it. |
| `curriculum` | `Syllabus → Chapter → Topic → (Lesson, Quiz, Exercise → ExerciseStep)`. Mirrors `bookademy-ai/app/schemas.py`. |
| `progress` | `StepCompletion` and `QuizAttempt`, plus the Check button's comparison. |
| `aiservice` | The HTTP client for `bookademy-ai`. Only Celery tasks use it. |

## API

| Method | Path | Does |
|---|---|---|
| `POST` | `/api/auth/register/` | Create an account |
| `POST` | `/api/auth/token/` | Sign in; returns the access/refresh pair |
| `POST` | `/api/auth/token/refresh/` | Rotate the pair |
| `GET` | `/api/auth/me/` | The signed-in user |
| `GET` `POST` | `/api/documents/` | List, or upload a PDF (multipart `file`) |
| `GET` `DELETE` | `/api/documents/<id>/` | Status and progress counts |
| `GET` | `/api/documents/<id>/syllabus/` | The table of contents, with this learner's ticks |
| `GET` | `/api/topics/<id>/` | Lesson, quiz and every exercise step |
| `POST` | `/api/steps/<id>/check/` | `{code}` → `{passed, first_mismatch_line, next_step_id}` |
| `POST` | `/api/quizzes/<id>/attempts/` | `{answers}` → score, and only then the answers |

Every query is scoped through `document__owner`, so one learner cannot read another's
course by guessing an id.

## Two things that look wrong and are not

**`expected_code` is sent to the browser.** It has to be: the ghost text a learner
types over is rendered from it. The check still runs on the server, which is what
actually writes the completion row — so `Next` cannot be reached by editing the page,
only the grey hint can be read early, and reading it early is the design.

**Topic completion is not a column.** It is derived on read from `StepCompletion` and
`QuizAttempt` (`progress/queries.py`, one aggregate per fact for a whole syllabus at
a time). A stored flag would be a second source of truth for something already
recorded.

## The generation pipeline

`documents/tasks.py`. `process_document` uploads the PDF, gets the syllabus, writes
the chapters and topics, then fans out one `generate_topic` task per topic.
`_settle_document` moves the document to `ready` once no topic is still in flight;
two topics finishing at once can both run it, which is harmless because they reach
the same answer.

`curriculum/builders.py` maps AI JSON to rows, apart from the Celery tasks so it can
be tested without a broker.

## Local setup

```bash
cp .env.example .env
docker compose up -d          # Postgres on 5434, Redis on 6379
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 8000
uv run celery -A config worker --loglevel=info   # separate terminal
```

Postgres is on 5434 because webshow already holds 5432 and 5433.

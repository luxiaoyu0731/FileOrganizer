# FileOrganizer

Turn scattered documents, spreadsheets, pictures and code into project folders. Review the proposed structure before moving files.

[中文](README.md) · [Usage guide](docs/usage.md)

![Project illustration](docs/media/project-hero.png)

Electron · React · FastAPI · Apache-2.0

[View the archive and restore result](docs/sample-result.md)

![Recorded walkthrough](docs/media/walkthrough.gif)

Recorded browser scan of synthetic files; no AI calls. The CLI example separately validates actual archiving and rollback.

## What you can do

- Group related files using summaries, embeddings and a configurable language model.
- Review and rename folders before confirming an archive operation.
- Copy, verify SHA-256, then remove the source; inspect operation history and restore unchanged archived files.

[Download the unsigned Mac Apple Silicon preview](https://github.com/luxiaoyu0731/FileOrganizer/releases/tag/v0.1.0-preview.1)

## Try it

Node.js 22.12+ or 24 LTS, Python 3.11+.

```sh
git clone https://github.com/luxiaoyu0731/FileOrganizer.git
cd FileOrganizer
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

Run the backend and frontend in separate terminals:

```sh
cd backend
venv/bin/uvicorn server:app --host 127.0.0.1 --port 18923
```

```sh
npm run dev:vite
```

Start with disposable files and a separate destination. Model requests may send filenames, paths and extracted summaries to your configured provider and incur charges. Keep this service on localhost. Rollback is conditional and does not replace backups.

## Offline sample

```sh
backend/venv/bin/python examples/try_archive.py --destination ../fileorganizer-sample
```

This creates its own synthetic files, executes the real archive and rollback code, and verifies restored contents. It makes no model calls; its manual categories are not an AI classification result.

<details><summary>Development</summary>

```sh
npm run typecheck
npm run build:frontend
python -m pytest backend/tests -q
```

[Code review](docs/code-review.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Asset credits](docs/media/README.md)

</details>

[Apache-2.0](LICENSE)

[Report a bug](https://github.com/luxiaoyu0731/FileOrganizer/issues/new?template=bug_report.yml) · [First-use feedback](https://github.com/luxiaoyu0731/FileOrganizer/issues/new?template=first_use.yml) · [Starter tasks](CONTRIBUTING.md)

[Versioned releases and artifact verification](docs/releasing.md)

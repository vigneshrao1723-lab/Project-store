"""Setup guides for the seeded projects, written from each project's own source, not from imagination.

Sources read on 14 Nov 2026:
* quantum-resistant-secure-communication: that repository's README.md (Technology Stack, Testing, Installation /
  Setup, Running the Application), crypto/kyber.py (ML-KEM-768), crypto/rsa.py (2048), crypto/aes.py (AES-256-GCM)
  and benchmark/benchmark_key_exchange.py (its usage lines).
* advanced-rag-knowledge-assistant: that repository's README.md (Quickstart, Running tests, evaluation harness),
  docs/AI_SETUP.md (local model, speech model, troubleshooting) and .env.example. (A first draft was written from an
  older, empty copy of the repository; it was replaced once the real one was found.)
* project-store-platform: this repository's README.md.
* smart-home-soc-fpga: the kit description in seed.py only (the project is not finished).

The format is the safe markdown subset in services/guide.py. An admin can edit a guide; once edited, `flask seed`
never overwrites it (Product.guide_edited).
"""

GUIDES = {
    "quantum-resistant-secure-communication": """# What you need
- Python 3.12 (the project is developed and tested against 3.12.10)
- PostgreSQL 17 or another recent PostgreSQL. SQLite is not supported: the server refuses a sqlite URL at start-up.
- Git

# Set it up
1. Unpack the kit or clone it, and open a terminal in the project folder.
2. Create and activate a virtual environment:
```
python -m venv venv
venv\\Scripts\\activate
```
3. Install the runtime dependencies, and the development ones if you will run the tests or the benchmark:
```
pip install -r requirements.txt
pip install -r requirements-dev.txt
```
4. Create an empty database in PostgreSQL: `CREATE DATABASE qrscs;`
5. Copy `.env.example` to `.env`, set `DATABASE_URL` (for example `postgresql+psycopg2://user:password@localhost:5432/qrscs`) and set `JWT_SECRET_KEY` to a real random value. The server refuses to start with the placeholder.
6. Apply the database migrations: `alembic upgrade head`
7. Generate the development TLS certificates (they are not shipped): `python scripts/generate_dev_certs.py`

# Run it
- Start the server from the project root, as a module: `python -m server.server`
- Start the desktop client in another terminal: `python main.py`
- Start more clients to try it with several users at once.

# Run the tests
The tests need the PostgreSQL database and `DATABASE_URL` from step 5; each test runs in a transaction that is rolled back.
```
pytest -q
```

# Run the benchmark
The key exchange is ML-KEM-768 (Kyber768) by default; RSA-2048 is there for the classical comparison. The benchmark times both, on the raw primitives and through the real session path, and writes the results as JSON:
```
python -m benchmark.benchmark_key_exchange
python -m benchmark.benchmark_key_exchange --iterations 500 --output results.json
```
Sample results are in `benchmark/results/key_exchange.json`. ML-KEM runs in pure Python (kyber-py) and RSA in compiled code, so compare sizes freely but read timings as this implementation's, not the algorithms'.

# Common problems
- "sqlite is not supported": point `DATABASE_URL` at PostgreSQL.
- The server will not start and mentions the JWT secret: set `JWT_SECRET_KEY` in `.env`.
- Import errors when starting the server: run it from the project root with `python -m server.server`, not as a file path.
- TLS errors on connect: run `python scripts/generate_dev_certs.py` again.
""",

    "advanced-rag-knowledge-assistant": """# What you need
- Docker Desktop (or Docker with Compose). Everything else runs in containers.
- Disk space for the free local language model (the Ollama image is about 3 to 4 GB, the model about 1.9 GB), and about 460 MB more for voice.
- No paid API key: embedding, reranking, speech and the default language model all run locally.

# Set it up
1. Unpack the kit or clone it, and open a terminal in the project folder.
2. Copy the settings file: `cp .env.example .env`. For anything beyond a throwaway local run, set `SECRET_KEY` to a real value (`openssl rand -hex 32`).
3. Start the stack (PostgreSQL with pgvector, Redis, Mailpit, the backend and the frontend). Database migrations run on start-up:
```
docker compose -f infra/compose/docker-compose.yml up --build
```
4. Install the free local language model once (Ollama). Until then the chat shows a banner and will not answer. With an NVIDIA GPU put `USE_GPU=1` in front of the command; to use a model server you already run, set `LLM_BASE_URL` and `LLM_MODEL` in `.env` instead:
```
infra/scripts/setup-local-llm.sh
```
5. For voice, install the speech model once: `infra/scripts/setup-local-stt.sh`

# Run it
1. Open http://localhost:3000, register and sign in.
2. Create a workspace, then upload a PDF, DOCX, TXT, Markdown or CSV file (up to 50 MiB) on the Documents page and wait for it to show `READY`.
3. Open Chat and ask a question. Click a numbered citation to see the exact source text. Try "Ask by voice" and "Play answer".

# Run the tests
```
cd backend && uv run pytest -q
cd frontend && npm run test -- --run
```
The backend tests need a reachable PostgreSQL. The retrieval evaluation: `cd backend && uv run python ../eval/scripts/run_retrieval_evaluation.py`

# Common problems
- "No AI model is set up": run `infra/scripts/setup-local-llm.sh`, or set `LLM_BASE_URL` and `LLM_MODEL`.
- "model server cannot be reached": start Ollama with `docker compose -f infra/compose/docker-compose.yml --profile llm up -d ollama`.
- "took too long": the model is slow on this CPU; use the GPU option, a smaller model, or raise `LLM_TIMEOUT_SECONDS`.
- A document stays `FAILED`: the Documents page shows the reason; check the file type and size.
""",

    "project-store-platform": """# What you need
- Python 3.12
- Git
- Docker Desktop, only if you want the MySQL setup with Docker Compose

# Set it up and run it (SQLite, no Docker)
1. Unpack the kit or clone it, and open a terminal in the project folder.
2. Create a virtual environment and install the dependencies:
```
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements-dev.txt
```
3. Point Flask at the app, create the tables and load the demo catalogue:
```
set FLASK_APP=wsgi.py
flask db upgrade
flask seed
flask run
```
4. Open http://127.0.0.1:5000. `flask seed` prints a generated admin password once; copy it.
5. To take practice payments without Razorpay keys, set `ALLOW_PRACTICE_GATEWAY=true` (demos only).

# Run it with Docker (MySQL)
1. Copy `.env.example` to `.env` and set `SECRET_KEY`, `DB_PASSWORD` and `DB_ROOT_PASSWORD`.
2. `docker compose up --build`, then open http://localhost:8000.

# Run the tests
```
pytest
pytest --cov=app --cov-report=term-missing
```
The concurrency tests need MySQL: set `TEST_DATABASE_URL` (see the README).

# Common problems
- "The database has no tables yet": run `flask db upgrade` before `flask seed`.
- The app refuses to start about `SECRET_KEY`: set a long random value (the README shows a command).
- Signed out after an upgrade: expected once, sessions carry a per-account token.
- Sign-in stops working over plain HTTP: leave `COOKIE_SECURE` off unless the site is on HTTPS.
""",

    "smart-home-soc-fpga": """# What you need
- An FPGA board and its vendor tools. The exact board and tool versions: see the project README.
- A Verilog and SystemVerilog simulator for the testbenches: see the project README.

# Set it up
1. Unpack the kit: it holds the RTL source, the testbenches and the synthesis notes.
2. Create a project in your FPGA tool and add the RTL source: see the synthesis notes and the project README.

# Run it
Synthesise and program the board as the synthesis notes describe: see the project README.

# Run the tests
Run the testbenches in your simulator: see the project README.

# Common problems
This project is still being finished and cannot be bought yet. The guide will be completed when it ships.
""",
}

"""Setup guides for the seeded projects, written from each project's own source, not from imagination.

Sources read on 14 Nov 2026:
* quantum-resistant-secure-communication: that repository's README.md (Technology Stack, Testing, Installation /
  Setup, Running the Application).
* advanced-rag-knowledge-assistant: that repository has no README or code yet, only empty design documents and an
  .env.example listing the settings it will need; every step that cannot be confirmed says "see the project README".
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

# Common problems
- "sqlite is not supported": point `DATABASE_URL` at PostgreSQL.
- The server will not start and mentions the JWT secret: set `JWT_SECRET_KEY` in `.env`.
- Import errors when starting the server: run it from the project root with `python -m server.server`, not as a file path.
- TLS errors on connect: run `python scripts/generate_dev_certs.py` again.
- Key exchange: the default is Kyber768 (ML-KEM-768); RSA-2048 can be selected for the classical comparison. Benchmarks: see the project README.
""",

    "advanced-rag-knowledge-assistant": """# What you need
- See the project README for the exact Python version and system packages.
- API keys for a language model and an embedding service. The project's settings name them `LLM_API_KEY` and `EMBEDDING_API_KEY`.
- A database URL and a secret key (`DATABASE_URL`, `SECRET_KEY`).
- Settings for file storage (`STORAGE_PROVIDER`, `STORAGE_BUCKET`) and, for voice, speech keys (`STT_API_KEY`, `TTS_API_KEY`).

# Set it up
1. Unpack the kit and open a terminal in the project folder.
2. Copy `.env.example` to `.env` and fill in the settings listed above.
3. Install the dependencies: see the project README.

# Run it
See the project README for the command that starts the app.

# Run the tests
See the project README.

# Common problems
- Answers fail straight away: check `LLM_API_KEY` and `EMBEDDING_API_KEY` in `.env`.
- Uploads fail: check `STORAGE_PROVIDER` and `STORAGE_BUCKET`.
- Anything else: see the project README, or use the contact form and we will help.
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

import os
import secrets

from .extensions import db
from .models import Category, InventoryLog, Product, User

CATEGORIES = [
    ("Security and cryptography", "security", "crypto"),
    ("AI and data", "ai-data", "ai"),
    ("Web and backend", "web-backend", "web"),
    ("Hardware and VLSI", "hardware-vlsi", "hardware"),
]

PRODUCTS = [
    dict(
        slug="quantum-resistant-secure-communication", category="security", featured=True,
        title="Quantum-Resistant Secure Communication System",
        tagline="An encrypted TLS messenger that benchmarks RSA-2048 against post-quantum ML-KEM-768 (Kyber768).",
        description=(
            "A working encrypted messenger: a PySide6 desktop client and a multi-user server over TLS sockets, "
            "backed by PostgreSQL. Each conversation's session key is set up with the post-quantum ML-KEM-768 "
            "(Kyber768) key exchange by default, or classical RSA-2048 for comparison, and messages and files are "
            "encrypted on the client with AES-256-GCM, so the server never sees the plaintext.\n\n"
            "The part most reports skip is the measurement. The kit's benchmark times key generation, key "
            "exchange and key recovery for both schemes, on the raw primitives and through the real session "
            "path, and records key and ciphertext sizes, so the comparison in your viva comes from your own "
            "runs, not a textbook table.\n\n"
            "Runs on a single laptop with Python and PostgreSQL. No cloud account needed."),
        tech="Python, ML-KEM-768 (Kyber768), RSA-2048, AES-256-GCM, TLS sockets, PySide6, PostgreSQL",
        includes="Client and server source with tests\nBenchmark script and sample results\nSetup guide\nArchitecture notes on the TLS transport and storage",
        delivery_url="",
        price=249900, stock=25),
    dict(
        slug="advanced-rag-knowledge-assistant", category="ai-data", featured=True,
        title="Advanced RAG Knowledge Assistant",
        tagline="Ask questions of your own documents and see exactly which passages the answer came from.",
        description=(
            "A multi-user retrieval-augmented generation platform end to end. Upload PDF, DOCX, TXT, Markdown "
            "or CSV files into a private workspace; the pipeline extracts, cleans, chunks, embeds and indexes "
            "them, and hybrid retrieval (pgvector dense search plus PostgreSQL full-text search, fused and "
            "reranked) finds the evidence for each question.\n\n"
            "Every answer carries numbered citations, and clicking one shows the exact source text. Ask by "
            "typing or by voice. It runs on free local models, so no paid API key is needed.\n\n"
            "An evaluation harness compares retrieval methods and chunking strategies with Recall@K, MRR and "
            "nDCG on a fixture document set."),
        tech="Python, FastAPI, PostgreSQL + pgvector, Redis, Next.js, TypeScript, Docker Compose",
        includes="Backend and frontend source with tests\nDocker Compose setup\nEvaluation harness and fixture documents\nSetup guide and design notes",
        delivery_url="",
        price=299900, stock=18),
    dict(
        slug="project-store-platform", category="web-backend", featured=True,
        title="Production E-Commerce Platform",
        tagline="The store you are standing in: catalogue, cart, transactional checkout and an admin dashboard.",
        description=(
            "A full-stack store with sign-in, a searchable catalogue, per-user carts and a checkout that "
            "holds stock inside a single database transaction, so two buyers can never take the last copy.\n\n"
            "Payments go through Razorpay test mode and are confirmed by signed callbacks. Orders, an "
            "inventory ledger and an admin dashboard sit behind a REST API with an automated test suite, a "
            "Dockerfile and a CI pipeline."),
        tech="Flask, MySQL, REST APIs, Docker, GitHub Actions, Razorpay",
        includes="Full source with tests\nDocker Compose setup\nCI workflow\nArchitecture and API notes",
        delivery_url="",
        price=199900, stock=30),
    dict(
        slug="smart-home-soc-fpga", category="hardware-vlsi", featured=False,
        title="Smart Home SoC on FPGA",
        tagline="A small system-on-chip for home control, written in Verilog and SystemVerilog.",
        description=(
            "A smart-home controller designed as an SoC and targeted at an FPGA.\n\n"
            "This project is still being finished. It is listed so you can see what is coming; it cannot be "
            "bought until it ships."),
        tech="Verilog, SystemVerilog, FPGA",
        includes="RTL source\nTestbenches\nSynthesis notes",
        delivery_url="", price=349900, stock=0),
]


# Catalogue copy that earlier versions seeded and that turned out not to match the projects' code (checked in v1.3:
# the messenger uses ML-KEM-768, not Kyber-1024, over TLS; the RAG assistant is FastAPI + pgvector + Next.js, not
# LangChain + FAISS + Streamlit). seed_copy_fixes() replaces a field only while it still holds this exact old text,
# so anything an admin has rewritten is left alone.
OLD_COPY = {
    "quantum-resistant-secure-communication": dict(
        tagline="A TCP client-server channel that benchmarks RSA-2048 against post-quantum Kyber-1024.",
        description=(
            "A working encrypted client-server framework over raw TCP sockets. It establishes a session with "
            "either classical RSA-2048 or the post-quantum Kyber-1024 key exchange, then carries real-time "
            "traffic under AES-256-GCM.\n\n"
            "The part most reports skip is the measurement. The kit records key generation latency, "
            "encryption and decryption throughput and computational overhead for both schemes side by side, "
            "so the comparison in your viva comes from your own runs, not a textbook table.\n\n"
            "Runs on a single laptop with Python. No cloud account needed."),
        tech="Python, Kyber-1024, RSA-2048, AES-256-GCM, TCP sockets",
        includes="Client and server source\nBenchmark scripts and sample results\nSetup guide for Windows and Linux\nArchitecture notes on the handshake"),
    "advanced-rag-knowledge-assistant": dict(
        description=(
            "A retrieval-augmented generation pipeline end to end: document ingestion, semantic chunking, "
            "transformer embeddings and FAISS vector search.\n\n"
            "The Streamlit interface shows source attribution next to every answer, along with a confidence "
            "estimate and live retrieval analytics, so you can see when the assistant is guessing.\n\n"
            "Point it at any folder of PDFs or text files."),
        tech="Python, LangChain, FAISS, Flask, Streamlit",
        includes="Ingestion and chunking pipeline\nStreamlit interface\nSample document set\nSetup guide and design notes"),
}


def _norm(text):
    return (text or "").replace("\r\n", "\n").strip()


def seed_copy_fixes():
    """Bring unedited catalogue copy up to date with the projects' code. Returns the number of fields changed."""
    specs = {spec["slug"]: spec for spec in PRODUCTS}
    changed = 0
    for slug, fields in OLD_COPY.items():
        p = db.session.scalar(db.select(Product).where(Product.slug == slug))
        if p is None:
            continue
        for field, old in fields.items():
            if _norm(getattr(p, field)) == _norm(old):
                setattr(p, field, specs[slug][field])
                changed += 1
    db.session.commit()
    return changed


def seed_guides():
    """Fill in the setup guide of each seeded project, unless an admin has edited it. Safe to run any number of times."""
    from .guides import GUIDES
    changed = 0
    for slug, text in GUIDES.items():
        p = db.session.scalar(db.select(Product).where(Product.slug == slug))
        if p is not None and not p.guide_edited and (p.setup_guide or "") != text:
            p.setup_guide = text
            changed += 1
    db.session.commit()
    return changed


def seed_catalogue(only_if_empty=False):
    if only_if_empty and db.session.scalar(db.select(db.func.count(Product.id))):
        seed_copy_fixes()             # an existing catalogue gets corrected copy (never over an edited field)
        seed_guides()                 # and the guides (never over an edited one)
        return False

    cats = {}
    for name, slug, kind in CATEGORIES:
        cat = db.session.scalar(db.select(Category).where(Category.slug == slug))
        if cat is None:
            cat = Category(name=name, slug=slug, cover_kind=kind)
            db.session.add(cat)
        cats[slug] = cat
    db.session.flush()

    for spec in PRODUCTS:
        if db.session.scalar(db.select(Product).where(Product.slug == spec["slug"])):
            continue
        p = Product(
            category_id=cats[spec["category"]].id, slug=spec["slug"], title=spec["title"],
            tagline=spec["tagline"], description=spec["description"], tech=spec["tech"],
            includes=spec["includes"], delivery_url=spec["delivery_url"],
            price_paise=spec["price"], stock=spec["stock"], featured=spec.get("featured", False),
        )
        db.session.add(p)
        db.session.flush()
        if p.stock:
            db.session.add(InventoryLog(product_id=p.id, delta=p.stock, reason="seed"))

    db.session.commit()
    seed_copy_fixes()
    seed_guides()
    return True


def seed_admin():
    """Create the first admin account if there is no admin yet.

    There is no built-in password. It comes from ADMIN_PASSWORD, and when that is not set a random one is
    generated. Returns None if an admin already exists, otherwise (email, generated_password) where
    generated_password is None when it came from ADMIN_PASSWORD. The caller shows a generated password once;
    it is stored only as a hash.
    """
    if db.session.scalar(db.select(User).where(User.role == "admin")):
        return None
    email = (os.getenv("ADMIN_EMAIL") or "admin@projectstore.local").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    generated = None
    if not password:
        password = generated = secrets.token_urlsafe(12)
    admin = User(name="Store admin", email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return email, generated

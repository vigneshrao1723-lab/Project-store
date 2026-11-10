import os

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
        includes="Client and server source\nBenchmark scripts and sample results\nSetup guide for Windows and Linux\nArchitecture notes on the handshake",
        delivery_url="",
        price=249900, stock=25),
    dict(
        slug="advanced-rag-knowledge-assistant", category="ai-data", featured=True,
        title="Advanced RAG Knowledge Assistant",
        tagline="Ask questions of your own documents and see exactly which passages the answer came from.",
        description=(
            "A retrieval-augmented generation pipeline end to end: document ingestion, semantic chunking, "
            "transformer embeddings and FAISS vector search.\n\n"
            "The Streamlit interface shows source attribution next to every answer, along with a confidence "
            "estimate and live retrieval analytics, so you can see when the assistant is guessing.\n\n"
            "Point it at any folder of PDFs or text files."),
        tech="Python, LangChain, FAISS, Flask, Streamlit",
        includes="Ingestion and chunking pipeline\nStreamlit interface\nSample document set\nSetup guide and design notes",
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


def seed_catalogue(only_if_empty=False):
    if only_if_empty and db.session.scalar(db.select(db.func.count(Product.id))):
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

    if not db.session.scalar(db.select(User).where(User.role == "admin")):
        # Demo credentials for local use. Set ADMIN_EMAIL and ADMIN_PASSWORD (or run
        # `flask create-admin`) for anything reachable from the internet.
        admin = User(name="Store admin", email=os.getenv("ADMIN_EMAIL", "admin@projectstore.local").lower(),
                     role="admin")
        admin.set_password(os.getenv("ADMIN_PASSWORD", "admin12345"))
        db.session.add(admin)
    db.session.commit()
    return True

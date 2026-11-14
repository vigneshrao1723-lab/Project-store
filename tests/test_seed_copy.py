"""The catalogue copy says what the projects' code does (checked against the repositories in v1.3), and correcting it
never overwrites a field an admin has rewritten."""
from app.extensions import db
from app.models import Product
from app.seed import OLD_COPY, PRODUCTS, seed_catalogue, seed_copy_fixes

SPECS = {spec["slug"]: spec for spec in PRODUCTS}


def product(slug):
    return db.session.scalar(db.select(Product).where(Product.slug == slug))


def test_the_messenger_copy_names_the_parameter_set_its_code_uses(app):
    qrsc = product("quantum-resistant-secure-communication")
    text = " ".join([qrsc.tagline, qrsc.description, qrsc.tech, qrsc.includes, qrsc.setup_guide])
    assert "ML-KEM-768" in text and "Kyber768" in text and "RSA-2048" in text and "AES-256-GCM" in text
    assert "1024" not in text and "TLS" in text
    assert "throughput" not in qrsc.description          # the benchmark times key setup; it never measured throughput


def test_the_rag_copy_names_its_real_stack(app):
    rag = product("advanced-rag-knowledge-assistant")
    text = " ".join([rag.tagline, rag.description, rag.tech, rag.includes, rag.setup_guide])
    for word in ("FastAPI", "pgvector", "Next.js", "citations"):
        assert word in text, word
    for word in ("Streamlit", "FAISS", "LangChain", "see the project README"):
        assert word not in text, word


def test_an_old_catalogue_gets_the_corrected_copy_but_an_edited_field_is_kept(app):
    qrsc = product("quantum-resistant-secure-communication")
    rag = product("advanced-rag-knowledge-assistant")
    for slug, fields in OLD_COPY.items():                 # a database seeded by v1.0 to v1.2
        p = product(slug)
        for field, old in fields.items():
            setattr(p, field, old.replace("\n", "\r\n") if field == "description" else old)
    qrsc.tech = "Python, my own words"                    # the owner rewrote this one field
    db.session.commit()

    changed = seed_copy_fixes()
    assert changed == sum(len(f) for f in OLD_COPY.values()) - 1
    db.session.refresh(qrsc), db.session.refresh(rag)
    assert qrsc.tech == "Python, my own words"
    assert qrsc.tagline == SPECS[qrsc.slug]["tagline"] and qrsc.description == SPECS[qrsc.slug]["description"]
    assert rag.tech == SPECS[rag.slug]["tech"] and rag.includes == SPECS[rag.slug]["includes"]
    assert seed_copy_fixes() == 0                         # idempotent


def test_seeding_an_existing_catalogue_applies_the_fixes(app):
    rag = product("advanced-rag-knowledge-assistant")
    rag.tech = OLD_COPY[rag.slug]["tech"]
    db.session.commit()
    assert seed_catalogue(only_if_empty=True) is False
    db.session.refresh(rag)
    assert rag.tech == SPECS[rag.slug]["tech"]

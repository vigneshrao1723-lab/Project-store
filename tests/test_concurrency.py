"""Real-database races. These need row locks, so they only run against MySQL/MariaDB.

    TEST_DATABASE_URL=mysql+pymysql://store:store@127.0.0.1:3306/project_store_test pytest tests/test_concurrency.py
"""
import os
import random
import threading

import pytest

from app.extensions import db
from app.models import CartItem, InventoryLog, Product, User
from app.services import orders as svc

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="needs MySQL or MariaDB row locks (set TEST_DATABASE_URL)")


def _run_threads(app, jobs):
    barrier = threading.Barrier(len(jobs))
    results = [None] * len(jobs)

    def runner(i, job):
        with app.app_context():
            try:
                barrier.wait(timeout=10)
                results[i] = job()
            except Exception as exc:  # collected and asserted on by the caller
                results[i] = exc
            finally:
                db.session.remove()

    threads = [threading.Thread(target=runner, args=(i, j)) for i, j in enumerate(jobs)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    return results


def _buyers(n):
    users = []
    for i in range(n):
        u = User(name=f"b{i}", email=f"b{i}@race.test")
        u.set_password("password123")
        db.session.add(u)
        users.append(u)
    db.session.commit()
    return [u.id for u in users]


def test_ten_buyers_race_for_three_copies(app):
    product = db.session.scalar(db.select(Product).where(Product.stock > 0))
    product.stock = 3
    pid = product.id
    ids = _buyers(10)
    for uid in ids:
        db.session.add(CartItem(user_id=uid, product_id=pid, qty=1))
    db.session.commit()

    def job(uid):
        def run():
            try:
                svc.create_order_from_cart(db.session.get(User, uid), "Racer")
                return "won"
            except svc.CheckoutError:
                return "lost"
        return run

    results = _run_threads(app, [job(uid) for uid in ids])
    assert not [r for r in results if isinstance(r, Exception)], results
    assert results.count("won") == 3 and results.count("lost") == 7
    db.session.expire_all()
    assert db.session.get(Product, pid).stock == 0


def test_mixed_baskets_never_deadlock_or_oversell(app):
    products = db.session.scalars(db.select(Product).where(Product.stock > 0).limit(3)).all()
    pids = [p.id for p in products]
    for p in products:
        p.stock = 5
    db.session.commit()
    ledger_before = {pid: db.session.scalar(db.select(db.func.coalesce(db.func.sum(InventoryLog.delta), 0))
                                            .where(InventoryLog.product_id == pid)) for pid in pids}
    ids = _buyers(16)
    rng = random.Random(7)
    for uid in ids:
        for pid in rng.sample(pids, rng.randint(2, 3)):       # different baskets, different orders
            db.session.add(CartItem(user_id=uid, product_id=pid, qty=rng.randint(1, 2)))
    db.session.commit()

    def job(uid):
        def run():
            try:
                svc.create_order_from_cart(db.session.get(User, uid), "Racer")
            except svc.CheckoutError:
                pass
            return "done"
        return run

    results = _run_threads(app, [job(uid) for uid in ids])
    assert all(r == "done" for r in results), results           # no deadlock errors, no crashes
    db.session.expire_all()
    for pid in pids:
        stock = db.session.get(Product, pid).stock
        assert 0 <= stock <= 5
        ledger = db.session.scalar(db.select(db.func.coalesce(db.func.sum(InventoryLog.delta), 0))
                                   .where(InventoryLog.product_id == pid))
        # Stock started at 5; every change since then must be recorded in the ledger.
        assert ledger - ledger_before[pid] == stock - 5


def test_a_double_click_on_checkout_makes_one_order_not_two(app):
    """Two simultaneous checkouts by the same user take turns on the user's row lock: one creates the order and the
    other is told about it (PendingOrderExists), so stock is held once, not twice."""
    products = db.session.scalars(db.select(Product).where(Product.stock > 0).limit(2)).all()
    for p in products:
        p.stock = 5
    ids = _buyers(1)
    for p in products:
        db.session.add(CartItem(user_id=ids[0], product_id=p.id, qty=1))
    db.session.commit()

    def run():
        try:
            return svc.create_order_from_cart(db.session.get(User, ids[0]), "Double Clicker").public_id
        except svc.PendingOrderExists as exc:
            return "existing:" + exc.order.public_id

    first, second = _run_threads(app, [run, run])
    assert not isinstance(first, Exception) and not isinstance(second, Exception), (first, second)
    created = [r for r in (first, second) if not r.startswith("existing:")]
    told = [r for r in (first, second) if r.startswith("existing:")]
    assert len(created) == 1 and told == ["existing:" + created[0]]
    db.session.expire_all()
    assert db.session.scalar(db.select(db.func.count()).select_from(db.select(svc.Order).where(svc.Order.status == "pending").subquery())) == 1
    assert [db.session.get(Product, p.id).stock for p in products] == [4, 4]

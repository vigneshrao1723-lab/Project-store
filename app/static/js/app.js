(() => {
  "use strict";
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";

  async function api(method, url, body) {
    const res = await fetch(url, {
      method, credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) {
      const err = new Error(data.error || "Something went wrong. Try again.");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // Indian digit grouping, matching the server's `inr` filter.
  function inr(paise) {
    const rupees = Math.floor(paise / 100), p = paise % 100;
    let s = String(rupees);
    if (s.length > 3) {
      let head = s.slice(0, -3), tail = s.slice(-3), parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head);
      s = parts.concat(tail).join(",");
    }
    return "₹" + s + (p ? "." + String(p).padStart(2, "0") : "");
  }

  function setCartCount(n) {
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = n; el.hidden = !n;
    });
  }

  // Quantity steppers (product page)
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-step]");
    if (!btn) return;
    const input = btn.parentElement.querySelector("input");
    const min = +input.min || 1, max = +input.max || 99;
    input.value = Math.max(min, Math.min(max, (+input.value || 1) + +btn.dataset.step));
  });

  // Add to cart (product page)
  document.querySelectorAll("[data-add-to-cart]").forEach((form) => {
    const note = form.closest(".buy").querySelector("[data-note]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submit = form.querySelector("button[type=submit]");
      submit.disabled = true;
      try {
        const cart = await api("POST", "/api/v1/cart/items", {
          product_id: +form.dataset.productId, qty: +form.qty.value || 1,
        });
        setCartCount(cart.count);
        note.innerHTML = 'Added to your cart. <a href="/cart">View cart</a> or <a href="/checkout">check out</a>.';
      } catch (err) {
        note.textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    });
  });

  // Cart page
  const cartRoot = document.querySelector("[data-cart]");
  if (cartRoot) {
    const showError = (msg) => {
      let el = cartRoot.querySelector(".cart-error");
      if (!el) {
        el = document.createElement("p");
        el.className = "flash flash-error cart-error";
        el.setAttribute("role", "alert");
        cartRoot.querySelector(".lines").prepend(el);
      }
      el.textContent = msg;
    };
    const render = (cart) => {
      cartRoot.querySelector(".cart-error")?.remove();
      setCartCount(cart.count);
      cartRoot.querySelector("[data-count]").textContent = cart.count;
      cartRoot.querySelector("[data-total]").textContent = inr(cart.total_paise);
      const byId = Object.fromEntries(cart.lines.map((l) => [String(l.product_id), l]));
      cartRoot.querySelectorAll("[data-line]").forEach((row) => {
        const l = byId[row.dataset.line];
        if (!l) { row.remove(); return; }
        row.querySelector("input").value = l.qty;
        row.querySelector("[data-line-total]").textContent = inr(l.line_paise);
      });
      if (!cart.lines.length) location.reload();
    };
    cartRoot.addEventListener("click", async (e) => {
      const row = e.target.closest("[data-line]");
      if (!row) return;
      const id = row.dataset.line;
      try {
        if (e.target.closest("[data-cart-remove]")) {
          render(await api("DELETE", `/api/v1/cart/items/${id}`));
        } else if (e.target.closest("[data-cart-step]")) {
          const input = row.querySelector("input");
          const qty = (+input.value || 1) + +e.target.closest("[data-cart-step]").dataset.cartStep;
          if (qty < 1) return;
          render(await api("PATCH", `/api/v1/cart/items/${id}`, { qty }));
        }
      } catch (err) { showError(err.message); }
    });
    cartRoot.addEventListener("change", async (e) => {
      const row = e.target.closest("[data-line]");
      if (!row || e.target.tagName !== "INPUT") return;
      try {
        render(await api("PATCH", `/api/v1/cart/items/${row.dataset.line}`, { qty: +e.target.value }));
      } catch (err) { showError(err.message); }
    });
  }

  // Countdown for held orders
  document.querySelectorAll("[data-expires]").forEach((box) => {
    const out = box.querySelector("[data-timer]");
    const end = Date.parse(box.dataset.expires);
    if (!out || Number.isNaN(end)) return;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      out.textContent = String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
      if (left === 0) { clearInterval(timer); setTimeout(() => location.reload(), 800); }
    };
    const timer = setInterval(tick, 1000);
    tick();
  });

  document.querySelectorAll("[data-autosubmit]").forEach((el) =>
    el.addEventListener("change", () => el.form.submit()));

  // A page restored from the back/forward cache is a frozen copy of how it looked when the user left it, for
  // example still signed in after they signed out. Reload it so it shows the current state. (Chrome skips the
  // cache for no-store pages; Safari and Firefox may not.)
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });
})();

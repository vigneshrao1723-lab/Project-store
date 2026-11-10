(() => {
  "use strict";
  const cfg = document.getElementById("rzp");
  const open = document.getElementById("rzp-open");
  const form = document.getElementById("rzp-verify");
  if (!cfg || !open || !form) return;

  open.addEventListener("click", () => {
    if (typeof Razorpay === "undefined") {
      alert("The payment window could not load. Check your connection and try again.");
      return;
    }
    const d = cfg.dataset;
    const rzp = new Razorpay({
      key: d.key,
      order_id: d.order,
      amount: +d.amount,
      currency: "INR",
      name: "Project Store",
      description: "Order " + d.publicId,
      prefill: { name: d.name, email: d.email, contact: d.phone },
      theme: { color: "#1B2A41" },
      handler: (resp) => {
        form.razorpay_order_id.value = resp.razorpay_order_id;
        form.razorpay_payment_id.value = resp.razorpay_payment_id;
        form.razorpay_signature.value = resp.razorpay_signature;
        form.submit();
      },
    });
    rzp.open();
  });
})();

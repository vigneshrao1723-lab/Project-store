"""Security audit A1: csp hardening."""




def test_a1_csp_hardening(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    directive = {p.split()[0]: p.split()[1:] for p in csp.split(";") if p.strip()}
    problems = []
    if "'unsafe-inline'" in directive.get("script-src", []):
        problems.append("script-src allows 'unsafe-inline'")
    if "'unsafe-inline'" in directive.get("style-src", []):
        problems.append("style-src allows 'unsafe-inline'")
    if not directive.get("frame-ancestors"):
        problems.append("no frame-ancestors directive (X-Frame-Options is the only clickjacking guard)")
    if "'self'" not in directive.get("form-action", []):
        problems.append("form-action is not restricted to 'self'")
    if "'self'" not in directive.get("base-uri", []) and "'none'" not in directive.get("base-uri", []):
        problems.append("base-uri is not restricted")
    assert not problems, problems

#!/usr/bin/env python3
"""Renew Instantly Google Calendar OAuth using Zapmail mailbox login.

Official Instantly-Google method: per-mailbox authorized-user refresh tokens.
Access tokens refresh in the worker. While the Google Cloud app is in Testing,
refresh tokens last 7 days — re-run this before then.

Writes GOOGLE_OUTREACH_CREDENTIAL_FILE (authorized_user_map). Never prints secrets.
Requires Playwright + pyotp. Zapmail key from Infisical unless ZAPMAIL_API_KEY is set.
"""
import json, os, time, urllib.parse, urllib.request, http.server, threading, subprocess
from pathlib import Path

REDIRECT = os.environ.get("GOOGLE_OAUTH_REDIRECT", "http://localhost:8502")
CLIENT_FILE = Path(os.environ.get(
    "GOOGLE_OAUTH_CLIENT_FILE",
    str(Path.home() / "Projects/Finished/CalendarInvites/"
        "client_secret_561758375651-ssp080mdsdhn1kc2bmibsrve2u9cs4d2.apps.googleusercontent.com.json")))
OUT = Path(os.environ.get("GOOGLE_OUTREACH_CREDENTIAL_FILE", "/tmp/google_outreach_credential.json"))
INF = os.path.expanduser("~/.pi/agent/skills/api-call/scripts/inf-secret")
REAUTH_BEFORE = 2 * 86400  # seconds; re-consent if refresh token expires within this
captured = {"path": None}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        captured["path"] = self.path
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a):
        pass


def zapmail_key():
    if os.environ.get("ZAPMAIL_API_KEY"):
        return os.environ["ZAPMAIL_API_KEY"]
    return subprocess.check_output([INF, "--entity", "wbg", "ZAPMAIL_API_KEY"], text=True).strip()


def mailboxes():
    key, found, page = zapmail_key(), {}, 1
    while page <= 20:
        req = urllib.request.Request(
            f"https://api.zapmail.ai/api/v2/mailboxes/list?page={page}&limit=50",
            headers={"x-auth-zapmail": key, "x-service-provider": "GOOGLE", "User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())["data"]
        for domain in data.get("domains") or []:
            for mailbox in domain.get("mailboxes") or []:
                email = (mailbox.get("email") or "").lower()
                if mailbox.get("status") == "ACTIVE" and mailbox.get("password") and mailbox.get("secret"):
                    found[email] = mailbox
        if not data.get("nextPage") or page >= data.get("totalPages", page):
            break
        page += 1
    return found


def load_out():
    if not OUT.exists():
        return {"type": "authorized_user_map", "accounts": {}}
    return json.loads(OUT.read_text())


def save_out(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    os.chmod(tmp, 0o600)
    tmp.replace(OUT)


def still_fresh(entry):
    expires = entry.get("refresh_expires_at") or 0
    return expires - time.time() > REAUTH_BEFORE and entry.get("refresh_token")


def exchange(client, code):
    data = urllib.parse.urlencode({
        "code": code, "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def oauth_one(page, client, email, mailbox):
    import pyotp
    captured["path"] = None
    params = {"client_id": client["client_id"], "redirect_uri": REDIRECT, "response_type": "code",
              "scope": "https://www.googleapis.com/auth/calendar", "access_type": "offline",
              "prompt": "consent", "login_hint": email}
    page.goto("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params),
              wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    if page.locator("input[type='email']").count():
        page.locator("input[type='email']").first.fill(email); page.keyboard.press("Enter"); page.wait_for_timeout(2000)
    if page.locator("input[type='password']").count():
        page.locator("input[type='password']").first.fill(mailbox["password"]); page.keyboard.press("Enter"); page.wait_for_timeout(2500)
    if "totp" in page.url or page.locator("input[type='tel'], #totpPin").count():
        page.locator("input[type='tel'], #totpPin").first.fill(pyotp.TOTP(mailbox["secret"].replace(" ", "")).now())
        page.keyboard.press("Enter"); page.wait_for_timeout(3000)
    for _ in range(25):
        if captured["path"] and "code=" in captured["path"]:
            break
        if "code=" in page.url and "localhost" in page.url:
            captured["path"] = "?" + page.url.split("?", 1)[-1]; break
        if page.locator("button:has-text('Allow')").count():
            page.locator("button:has-text('Allow')").first.click(); page.wait_for_timeout(2000); continue
        page.wait_for_timeout(400)
    qs = urllib.parse.parse_qs((captured["path"] or "").split("?", 1)[-1])
    code = (qs.get("code") or [None])[0]
    if not code:
        return None, "no_code"
    tok = exchange(client, code)
    if not tok.get("refresh_token"):
        return None, "missing_refresh"
    return {"refresh_token": tok["refresh_token"], "granted_at": int(time.time()),
            "refresh_expires_at": int(time.time()) + int(tok.get("refresh_token_expires_in") or 7 * 86400)}, "granted"


def main():
    from playwright.sync_api import sync_playwright
    web = json.loads(CLIENT_FILE.read_text())["web"]
    client = {"client_id": web["client_id"], "client_secret": web["client_secret"]}
    payload = load_out()
    payload.update(type="authorized_user_map", client_id=client["client_id"],
                   client_secret=client["client_secret"], token_uri="https://oauth2.googleapis.com/token")
    payload.setdefault("accounts", {})
    boxes = mailboxes()
    httpd = http.server.HTTPServer(("127.0.0.1", int(urllib.parse.urlparse(REDIRECT).port or 8502)), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for email, mailbox in sorted(boxes.items()):
            entry = payload["accounts"].get(email) or {}
            if still_fresh(entry):
                print(email, "fresh"); continue
            context = browser.new_context(); page = context.new_page()
            try:
                granted, status = oauth_one(page, client, email, mailbox)
            except Exception as error:
                granted, status = None, type(error).__name__
            context.close()
            if granted:
                payload["accounts"][email] = granted
                save_out(payload)
            print(email, status)
        browser.close()
    httpd.shutdown()
    save_out(payload)
    print("accounts", len(payload["accounts"]))


if __name__ == "__main__":
    main()

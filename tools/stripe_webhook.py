#!/usr/bin/env python3
"""
ThreadIntel — Stripe Webhook Handler

Listens for Stripe events and automatically activates subscribers in Supabase
the moment payment is confirmed. No manual steps required.

Setup:
  1. pip install flask stripe supabase python-dotenv
  2. Add to .env:
       STRIPE_WEBHOOK_SECRET=whsec_...   (from Stripe Dashboard → Webhooks)
       STRIPE_SECRET_KEY=sk_live_...
       SUPABASE_URL=...
       SUPABASE_KEY=...
  3. Run: python tools/stripe_webhook.py
  4. In Stripe Dashboard → Webhooks, set endpoint to:
       https://YOUR_SERVER/webhook
     and select events:
       - checkout.session.completed
       - customer.subscription.created
       - customer.subscription.deleted

Local testing with Stripe CLI:
  stripe listen --forward-to localhost:5001/webhook
"""

import os, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from flask import Flask, request, jsonify
import stripe

stripe.api_key         = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET         = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SUPABASE_URL           = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY           = os.getenv("SUPABASE_KEY", "")
ADMIN_EMAIL            = os.getenv("ADMIN_EMAIL", "syed.aayan.rehman@gmail.com")

app = Flask(__name__)


def _supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _activate_subscriber(email: str, name: str = "", stripe_customer_id: str = ""):
    """
    Upsert the subscriber row: set active=True, plan='pro'.
    Creates the row if it doesn't exist (e.g. subscriber paid directly without waitlist).
    """
    sb = _supabase()
    existing = sb.table("subscribers").select("id, active").eq("email", email).limit(1).execute().data

    if existing:
        sb.table("subscribers").update({
            "active": True,
            "plan": "pro",
            "stripe_customer_id": stripe_customer_id,
        }).eq("email", email).execute()
        print(f"  ✓ Activated existing subscriber: {email}")
    else:
        sb.table("subscribers").insert({
            "email": email,
            "name": name,
            "active": True,
            "plan": "pro",
            "stripe_customer_id": stripe_customer_id,
        }).execute()
        print(f"  ✓ Created + activated new subscriber: {email}")

    _send_welcome_email(email, name.split()[0] if name else "there")


def _deactivate_subscriber(email: str):
    """Cancel subscription — set active=False."""
    sb = _supabase()
    sb.table("subscribers").update({"active": False, "plan": "cancelled"}).eq("email", email).execute()
    print(f"  ↓ Deactivated subscriber: {email}")


def _send_welcome_email(email: str, first_name: str):
    """Send a welcome email with portal access link."""
    try:
        import base64
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "threadintel"))
        from email_brief import _get_gmail_service
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        portal_url = "https://threadintel.io/portal.html"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;
                    background:#020818;color:#E2E8F0;padding:40px 32px;border-radius:16px;">
          <div style="font-size:24px;font-weight:800;margin-bottom:4px;">
            Welcome to Thread<em style="color:#7C6FFF;">Intel</em>
          </div>
          <div style="height:2px;background:linear-gradient(90deg,#7C6FFF,#00D9B8);
                      margin:16px 0 32px;border-radius:2px;"></div>

          <p style="font-size:17px;font-weight:700;color:#fff;margin-bottom:8px;">
            Hi {first_name}, you're in. 🎉
          </p>
          <p style="color:#94A3B8;line-height:1.7;margin-bottom:32px;">
            Your subscription is active. Open your portal, submit a research topic,
            and your first report will be in your inbox in under 30 minutes.
            Completely automated — no waiting on a human.
          </p>

          <a href="{portal_url}"
             style="display:inline-block;background:linear-gradient(135deg,#7C6FFF,#5A4FE0);
                    color:#fff;font-weight:800;font-size:16px;padding:16px 36px;
                    border-radius:12px;text-decoration:none;box-shadow:0 0 40px rgba(124,111,255,.4);">
            Open Your Portal →
          </a>

          <div style="margin-top:40px;padding-top:24px;border-top:1px solid rgba(255,255,255,.06);">
            <p style="font-size:13px;color:#94A3B8;margin-bottom:12px;font-weight:700;">
              Quick start:
            </p>
            <ol style="color:#94A3B8;font-size:13px;line-height:2;padding-left:20px;">
              <li>Click "Open Your Portal" above</li>
              <li>Enter your email to receive a magic login link</li>
              <li>Type any research topic — as broad or specific as you like</li>
              <li>Choose your format (Email, Slides, Docs, or Sheets)</li>
              <li>Hit submit — report in under 30 minutes</li>
            </ol>
          </div>

          <div style="margin-top:32px;font-size:12px;color:#4A5568;line-height:1.6;">
            Questions? Just reply to this email.<br>
            ThreadIntel · <a href="{portal_url}" style="color:#7C6FFF;">threadintel.io</a>
          </div>
        </div>"""

        service = _get_gmail_service()
        msg = MIMEMultipart("alternative")
        msg["to"]      = email
        msg["from"]    = "me"
        msg["subject"] = "Welcome to ThreadIntel — your portal is open"
        msg.attach(MIMEText(html, "html", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"  ✉  Welcome email sent to {email}")
    except Exception as e:
        print(f"  ⚠  Welcome email failed for {email}: {e}")


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    payload   = request.get_data()
    sig       = request.headers.get("Stripe-Signature", "")

    # Verify signature
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        print("  ✗ Invalid Stripe signature")
        return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        print(f"  ✗ Webhook parse error: {e}")
        return jsonify({"error": str(e)}), 400

    etype = event["type"]
    data  = event["data"]["object"]
    print(f"  → Stripe event: {etype}")

    if etype == "checkout.session.completed":
        email       = data.get("customer_email") or (data.get("customer_details") or {}).get("email", "")
        customer_id = data.get("customer", "")
        name        = (data.get("customer_details") or {}).get("name", "")
        if email:
            _activate_subscriber(email, name, customer_id)

    elif etype == "customer.subscription.created":
        customer_id = data.get("customer", "")
        if customer_id:
            try:
                customer    = stripe.Customer.retrieve(customer_id)
                email       = customer.get("email", "")
                name        = customer.get("name", "")
                if email:
                    _activate_subscriber(email, name, customer_id)
            except Exception as e:
                print(f"  ⚠ Could not fetch customer {customer_id}: {e}")

    elif etype == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        if customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                email    = customer.get("email", "")
                if email:
                    _deactivate_subscriber(email)
            except Exception as e:
                print(f"  ⚠ Could not fetch customer {customer_id}: {e}")

    return jsonify({"received": True}), 200


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ThreadIntel Stripe Webhook"}), 200


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", 5001))
    print(f"\n  ThreadIntel Stripe Webhook — listening on port {port}")
    print(f"  Endpoint: POST http://localhost:{port}/webhook")
    print(f"  Health:   GET  http://localhost:{port}/health")
    print(f"\n  To test locally:")
    print(f"    stripe listen --forward-to localhost:{port}/webhook\n")
    app.run(host="0.0.0.0", port=port, debug=False)

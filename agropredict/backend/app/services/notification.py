"""
AgroPredict - Notification Service (Slack, HTTP Email APIs & SMTP)

Handles sending alerts, daily price update summaries, and advisories to Slack channels 
and via HTTP Email APIs (Resend/Brevo/SendGrid) or SMTP Email to all registered users.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Dict, Any
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.commodity import User

logger = logging.getLogger(__name__)


def send_slack_notification(title: str, message: str, details: Optional[dict] = None) -> Dict[str, Any]:
    """
    Sends a formatted notification block to the configured Slack Webhook URL.
    Returns a dict with 'success' boolean and 'message' description.
    """
    settings = get_settings()
    webhook_url = settings.SLACK_WEBHOOK_URL.strip() if settings.SLACK_WEBHOOK_URL else ""
    if not webhook_url:
        msg = "Slack Webhook URL is not configured. Set SLACK_WEBHOOK_URL in environment variables on Render."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg}

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🌾 {title}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message
            }
        }
    ]

    if details:
        fields = []
        for k, v in details.items():
            fields.append({"type": "mrkdwn", "text": f"*{k}:*\n{v}"})
        blocks.append({
            "type": "section",
            "fields": fields[:10]  # Limit Slack fields
        })

    payload = {"blocks": blocks}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.info(f"[Notification] Slack message sent successfully for '{title}'.")
                return {"success": True, "message": "Slack message sent successfully."}
            else:
                err_msg = f"Slack API returned status {response.status_code}: {response.text}"
                logger.error(f"[Notification] {err_msg}")
                return {"success": False, "message": err_msg}
    except Exception as e:
        err_msg = f"Exception sending Slack notification: {str(e)}"
        logger.error(f"[Notification] {err_msg}")
        return {"success": False, "message": err_msg}


def _send_email_via_resend(api_key: str, from_email: str, recipients: List[str], subject: str, body_html: str) -> Dict[str, Any]:
    """Sends email via Resend HTTP API (Port 443 - works on Render without port blocking)."""
    try:
        # Use onboarding@resend.dev for Resend free tier compatibility
        sender = "AgroPredict <onboarding@resend.dev>"
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": sender,
            "to": recipients,
            "subject": f"🌾 AgroPredict: {subject}",
            "html": body_html
        }
        if from_email and "@" in from_email and "resend.dev" not in from_email:
            payload["reply_to"] = from_email

        with httpx.Client(timeout=10.0) as client:
            res = client.post("https://api.resend.com/emails", headers=headers, json=payload)
            if res.status_code in [200, 201]:
                logger.info(f"[Notification] Email sent via Resend HTTP API to {recipients}.")
                return {"success": True, "message": f"Email sent via Resend API to {len(recipients)} recipient(s).", "recipients": recipients}
            elif res.status_code == 403 and "only send testing emails to your own email address" in res.text:
                # Resend Free Tier restriction: Only allows sending to account owner email during testing
                owner_target = [from_email] if (from_email and "@" in from_email) else recipients[:1]
                logger.warning(f"[Notification] Resend Free restriction hit. Retrying send to account owner: {owner_target}")
                payload["to"] = owner_target
                retry_res = client.post("https://api.resend.com/emails", headers=headers, json=payload)
                if retry_res.status_code in [200, 201]:
                    msg_text = f"Email sent via Resend to account owner ({owner_target[0]}). (Note: Resend free tier requires domain verification at resend.com/domains to email other addresses)."
                    logger.info(f"[Notification] {msg_text}")
                    return {"success": True, "message": msg_text, "recipients": owner_target}
                else:
                    err_msg = f"Resend API error ({retry_res.status_code}): {retry_res.text}"
                    logger.error(f"[Notification] {err_msg}")
                    return {"success": False, "message": err_msg, "recipients": recipients}
            else:
                err_msg = f"Resend API error ({res.status_code}): {res.text}"
                logger.error(f"[Notification] {err_msg}")
                return {"success": False, "message": err_msg, "recipients": recipients}
    except Exception as e:
        err_msg = f"Exception sending via Resend API: {str(e)}"
        logger.error(f"[Notification] {err_msg}")
        return {"success": False, "message": err_msg, "recipients": recipients}


def _send_email_via_brevo(api_key: str, from_email: str, recipients: List[str], subject: str, body_html: str) -> Dict[str, Any]:
    """Sends email via Brevo / Sendinblue HTTP API (Port 443 - works on Render)."""
    try:
        sender_email = from_email if "@" in from_email else "noreply@agropredict.com"
        headers = {
            "api-key": api_key.strip(),
            "Content-Type": "application/json"
        }
        payload = {
            "sender": {"name": "AgroPredict", "email": sender_email},
            "to": [{"email": r} for r in recipients],
            "subject": f"🌾 AgroPredict: {subject}",
            "htmlContent": body_html
        }
        with httpx.Client(timeout=10.0) as client:
            res = client.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=payload)
            if res.status_code in [200, 201, 202]:
                logger.info(f"[Notification] Email sent via Brevo HTTP API to {recipients}.")
                return {"success": True, "message": f"Email sent via Brevo API to {len(recipients)} recipient(s).", "recipients": recipients}
            else:
                err_msg = f"Brevo API error ({res.status_code}): {res.text}"
                logger.error(f"[Notification] {err_msg}")
                return {"success": False, "message": err_msg, "recipients": recipients}
    except Exception as e:
        err_msg = f"Exception sending via Brevo API: {str(e)}"
        logger.error(f"[Notification] {err_msg}")
        return {"success": False, "message": err_msg, "recipients": recipients}


def send_email_notification(
    to_emails: List[str],
    subject: str,
    body_html: str,
    body_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends an Email to a list of target email addresses using HTTP Email APIs or SMTP.
    Supports HTTP API fallbacks (Resend / Brevo) to bypass cloud SMTP port blocking.
    """
    settings = get_settings()

    if not to_emails:
        msg = "No target recipient email addresses provided."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": []}

    recipients = list(set([e.strip() for e in to_emails if e and "@" in e]))
    if not recipients:
        msg = "No valid recipient email addresses after validation."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": []}

    smtp_user = settings.SMTP_USER.strip() if settings.SMTP_USER else ""
    smtp_pass = settings.SMTP_PASSWORD.strip() if settings.SMTP_PASSWORD else ""
    smtp_host = settings.SMTP_HOST.strip() if settings.SMTP_HOST else ""
    smtp_port = settings.SMTP_PORT or 587

    # 1. Primary HTTP API Check (Resend API Key)
    if settings.RESEND_API_KEY.strip():
        logger.info("[Notification] RESEND_API_KEY detected. Using Resend HTTP API...")
        return _send_email_via_resend(settings.RESEND_API_KEY, smtp_user, recipients, subject, body_html)

    # 2. Secondary HTTP API Check (Brevo API Key)
    if settings.BREVO_API_KEY.strip():
        logger.info("[Notification] BREVO_API_KEY detected. Using Brevo HTTP API...")
        return _send_email_via_brevo(settings.BREVO_API_KEY, smtp_user, recipients, subject, body_html)

    # 3. SMTP Socket Fallback (Port 587 / 465)
    if not smtp_host and smtp_user and "@gmail.com" in smtp_user.lower():
        smtp_host = "smtp.gmail.com"

    if not smtp_user or not smtp_pass:
        msg = (
            "No Email credentials configured. On Render, raw SMTP ports 587/465 are blocked by default. "
            "Please set RESEND_API_KEY (from resend.com - free) or BREVO_API_KEY in Render environment variables for instant HTTP email delivery."
        )
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": recipients}

    if not smtp_host:
        smtp_host = "smtp.gmail.com"

    msg_mime = MIMEMultipart("alternative")
    msg_mime["Subject"] = f"🌾 AgroPredict: {subject}"
    msg_mime["From"] = smtp_user
    msg_mime["To"] = ", ".join(recipients)

    if body_text:
        msg_mime.attach(MIMEText(body_text, "plain"))
    msg_mime.attach(MIMEText(body_html, "html"))

    # Attempt SMTP STARTTLS (587)
    try:
        logger.info(f"[Notification] Connecting to SMTP {smtp_host}:{smtp_port} for {smtp_user}...")
        server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg_mime.as_string())
        server.quit()
        return {"success": True, "message": f"Email sent via SMTP to {len(recipients)} recipient(s).", "recipients": recipients}
    except smtplib.SMTPAuthenticationError:
        err_msg = "Gmail SMTP Bad Credentials. Use a 16-character Gmail App Password (Google Account > Security > App Passwords)."
        logger.error(f"[Notification] {err_msg}")
        return {"success": False, "message": err_msg, "recipients": recipients}
    except OSError as net_err:
        if "Network is unreachable" in str(net_err) or "101" in str(net_err) or "111" in str(net_err):
            err_msg = (
                "Render cloud host blocks raw SMTP ports 587/465 ('Network is unreachable'). "
                "Solution: Add a free RESEND_API_KEY (from resend.com - 3000 free emails/month) or BREVO_API_KEY to your Render Environment Variables."
            )
            logger.error(f"[Notification] {err_msg}")
            return {"success": False, "message": err_msg, "recipients": recipients}
        logger.warning(f"[Notification] STARTTLS error: {net_err}. Retrying SSL 465...")

    # Attempt SMTP SSL (465)
    try:
        ssl_server = smtplib.SMTP_SSL(smtp_host, 465, timeout=10)
        ssl_server.ehlo()
        ssl_server.login(smtp_user, smtp_pass)
        ssl_server.sendmail(smtp_user, recipients, msg_mime.as_string())
        ssl_server.quit()
        return {"success": True, "message": f"Email sent via SSL to {len(recipients)} recipient(s).", "recipients": recipients}
    except Exception as e:
        err_msg = (
            f"SMTP failed ({str(e)}). Render cloud blocks raw SMTP ports 587/465. "
            "Please add RESEND_API_KEY (resend.com) or BREVO_API_KEY in Render environment variables for HTTPS delivery."
        )
        logger.error(f"[Notification] {err_msg}")
        return {"success": False, "message": err_msg, "recipients": recipients}


def get_all_registered_user_emails(db: Session) -> List[str]:
    """Retrieves all registered user emails from the database."""
    try:
        stmt = select(User.email).where(User.email.isnot(None))
        results = db.execute(stmt).scalars().all()
        emails = [e for e in results if e and "@" in e]
        
        # Include default admin notification email if present in env settings
        settings = get_settings()
        if settings.NOTIFICATION_EMAIL and settings.NOTIFICATION_EMAIL not in emails:
            emails.append(settings.NOTIFICATION_EMAIL)

        return emails
    except Exception as e:
        logger.error(f"[Notification] Error fetching user emails: {e}")
        return []


def broadcast_daily_update(db: Session, update_summary: Optional[dict] = None) -> dict:
    """
    Broadcasts daily commodity & forecast updates to Slack and to ALL registered user emails.
    """
    settings = get_settings()
    user_emails = get_all_registered_user_emails(db)

    title = "Daily Agriculture & Price Ingestion Update"
    summary_text = (
        "Daily automated ingestion of Mandi price observations and weather covariates "
        "has completed successfully. Updated market trends and AI advisories are live on the dashboard."
    )

    details = update_summary or {
        "Status": "Completed",
        "Frontend Dashboard": settings.FRONTEND_URL
    }

    # 1. Send Slack Notification
    slack_res = send_slack_notification(title, summary_text, details)

    # 2. Send Email Notification to Registered Users
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #18181b; color: #f4f4f5; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #27272a; border-radius: 8px; padding: 24px; border: 1px solid #3f3f46;">
            <h2 style="color: #22c55e; margin-top: 0;">🌾 AgroPredict Market Alert</h2>
            <p style="color: #e4e4e7; font-size: 16px; line-height: 1.5;">
                Hello from AgroPredict! The daily automated dataset ingestion and Chronos-2 price forecast update is now complete.
            </p>
            <div style="background-color: #18181b; padding: 16px; border-radius: 6px; margin: 16px 0;">
                <h4 style="margin: 0 0 8px 0; color: #a1a1aa;">Summary</h4>
                <p style="margin: 0; color: #f4f4f5;">{summary_text}</p>
            </div>
            <a href="{settings.FRONTEND_URL}" style="display: inline-block; background-color: #22c55e; color: #000; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 12px;">
                View Live Forecasts & Advisories
            </a>
            <p style="font-size: 12px; color: #71717a; margin-top: 24px;">
                You are receiving this email because you are a registered user on AgroPredict.
            </p>
        </div>
    </body>
    </html>
    """

    email_res = send_email_notification(
        to_emails=user_emails,
        subject="Daily Market Data & Forecast Update",
        body_html=html_content,
        body_text=f"AgroPredict Daily Market Alert:\n\n{summary_text}\n\nVisit: {settings.FRONTEND_URL}"
    )

    return {
        "slack": slack_res,
        "email": email_res,
        "recipient_count": len(user_emails),
        "recipients": user_emails
    }


def notify_ingestion_event(commodity_name: str, mandi_name: str, state: str, record_count: int, db: Session, user_email: Optional[str] = None) -> dict:
    """
    Sends Slack and Email notifications whenever data ingestion is executed (dynamically or manually).
    """
    settings = get_settings()
    title = f"Data Ingestion Triggered: {commodity_name} at {mandi_name}"
    summary_text = (
        f"Fresh market data ingestion executed for {commodity_name} in {mandi_name}, {state}. "
        f"Successfully processed {record_count} price observations and updated AI models."
    )
    details = {
        "Commodity": commodity_name,
        "Mandi": mandi_name,
        "State": state,
        "Records Processed": str(record_count),
        "Frontend": settings.FRONTEND_URL
    }

    # 1. Slack notification
    slack_res = send_slack_notification(title, summary_text, details)

    # 2. Email recipients: user_email if specified + all registered users
    target_emails = [user_email] if user_email else []
    registered_emails = get_all_registered_user_emails(db)
    recipients = list(set([e for e in target_emails + registered_emails if e and "@" in e]))

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #18181b; color: #f4f4f5; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #27272a; border-radius: 8px; padding: 24px; border: 1px solid #3f3f46;">
            <h2 style="color: #22c55e; margin-top: 0;">🌾 AgroPredict Ingestion Alert</h2>
            <p style="color: #e4e4e7; font-size: 16px; line-height: 1.5;">
                Data ingestion was executed for <strong>{commodity_name}</strong> at <strong>{mandi_name}, {state}</strong>.
            </p>
            <div style="background-color: #18181b; padding: 16px; border-radius: 6px; margin: 16px 0;">
                <p style="margin: 0; color: #f4f4f5;"><strong>Records Processed:</strong> {record_count}</p>
                <p style="margin: 4px 0 0 0; color: #a1a1aa;">{summary_text}</p>
            </div>
            <a href="{settings.FRONTEND_URL}" style="display: inline-block; background-color: #22c55e; color: #000; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 12px;">
                View Live Forecast & Analytics
            </a>
        </div>
    </body>
    </html>
    """

    email_res = send_email_notification(
        to_emails=recipients,
        subject=f"Market Ingestion: {commodity_name} ({mandi_name})",
        body_html=html_content,
        body_text=summary_text
    )

    return {
        "slack": slack_res,
        "email": email_res,
        "recipients": recipients
    }


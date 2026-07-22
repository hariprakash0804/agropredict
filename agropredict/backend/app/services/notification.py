"""
AgroPredict - Notification Service (Slack & Gmail/SMTP Email)

Handles sending alerts, daily price update summaries, and advisories to Slack channels 
and via Gmail/SMTP Email to all registered user email addresses.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple, Dict, Any
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
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        msg = "Slack Webhook URL is not configured. Please set SLACK_WEBHOOK_URL in environment variables."
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


def send_email_notification(
    to_emails: List[str],
    subject: str,
    body_html: str,
    body_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends an Email to a list of target email addresses using Gmail or SMTP settings.
    Automatically detects Gmail configurations and handles STARTTLS (587) / SSL (465).
    """
    settings = get_settings()

    smtp_user = settings.SMTP_USER.strip() if settings.SMTP_USER else ""
    smtp_pass = settings.SMTP_PASSWORD.strip() if settings.SMTP_PASSWORD else ""
    smtp_host = settings.SMTP_HOST.strip() if settings.SMTP_HOST else ""
    smtp_port = settings.SMTP_PORT or 587

    # Smart auto-detection for Gmail
    if not smtp_host and smtp_user and "@gmail.com" in smtp_user.lower():
        smtp_host = "smtp.gmail.com"
        smtp_port = 587

    if not smtp_user or not smtp_pass:
        msg = "SMTP credentials missing. Please set SMTP_USER and SMTP_PASSWORD (or Gmail App Password) in environment variables."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": []}

    if not smtp_host:
        smtp_host = "smtp.gmail.com"  # Default fallback to Gmail SMTP

    if not to_emails:
        msg = "No target recipient email addresses provided."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": []}

    # Clean and deduplicate recipient emails
    recipients = list(set([e.strip() for e in to_emails if e and "@" in e]))
    if not recipients:
        msg = "No valid recipient email addresses after validation."
        logger.info(f"[Notification] {msg}")
        return {"success": False, "message": msg, "recipients": []}

    # Construct MIMEMultipart email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌾 AgroPredict: {subject}"
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)

    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    # Connection attempt 1: STARTTLS (Port 587 or default)
    try:
        logger.info(f"[Notification] Connecting to SMTP server {smtp_host}:{smtp_port} for user {smtp_user}...")
        server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()

        logger.info(f"[Notification] Email sent successfully to {len(recipients)} recipient(s): {recipients}")
        return {"success": True, "message": f"Email sent successfully to {len(recipients)} recipient(s).", "recipients": recipients}

    except smtplib.SMTPAuthenticationError as auth_err:
        err_msg = (
            "Gmail SMTP Authentication Failed (535 Bad Credentials). "
            "If using Gmail, you MUST use a 16-character 'App Password' generated from "
            "Google Account > Security > 2-Step Verification > App Passwords."
        )
        logger.error(f"[Notification] {err_msg} Details: {auth_err}")
        return {"success": False, "message": err_msg, "recipients": recipients}

    except Exception as e1:
        logger.warning(f"[Notification] STARTTLS connection attempt failed: {e1}. Retrying with SSL (Port 465)...")
        # Connection attempt 2: SSL (Port 465 fallback)
        try:
            ssl_server = smtplib.SMTP_SSL(smtp_host, 465, timeout=15)
            ssl_server.ehlo()
            ssl_server.login(smtp_user, smtp_pass)
            ssl_server.sendmail(smtp_user, recipients, msg.as_string())
            ssl_server.quit()

            logger.info(f"[Notification] Email sent via SSL (465) successfully to {len(recipients)} recipient(s).")
            return {"success": True, "message": f"Email sent successfully via SSL to {len(recipients)} recipient(s).", "recipients": recipients}
        except smtplib.SMTPAuthenticationError:
            err_msg = (
                "Gmail SMTP Authentication Failed. Make sure to use a 16-character Gmail App Password "
                "(Google Account > Security > 2-Step Verification > App Passwords)."
            )
            logger.error(f"[Notification] {err_msg}")
            return {"success": False, "message": err_msg, "recipients": recipients}
        except Exception as e2:
            err_msg = f"Failed to send email via SMTP: {str(e2)}"
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

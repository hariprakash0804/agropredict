"""
AgroPredict - Notification Service (Slack & SMTP Email)

Handles sending alerts, daily price update summaries, and advisories to Slack channels 
and via SMTP Email to all registered user email addresses.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.commodity import User

logger = logging.getLogger(__name__)


def send_slack_notification(title: str, message: str, details: Optional[dict] = None) -> bool:
    """
    Sends a formatted notification block to the configured Slack Webhook URL.
    Returns True if successful, False otherwise.
    """
    settings = get_settings()
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.info("[Notification] Slack Webhook URL not configured. Skipping Slack alert.")
        return False

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
                return True
            else:
                logger.error(f"[Notification] Slack API error ({response.status_code}): {response.text}")
                return False
    except Exception as e:
        logger.error(f"[Notification] Exception sending Slack notification: {e}")
        return False


def send_email_notification(
    to_emails: List[str],
    subject: str,
    body_html: str,
    body_text: Optional[str] = None
) -> bool:
    """
    Sends an SMTP Email to a list of target email addresses using configured SMTP settings.
    """
    settings = get_settings()
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.info("[Notification] SMTP host or user not configured. Skipping Email dispatch.")
        return False

    if not to_emails:
        logger.info("[Notification] No target email addresses provided.")
        return False

    # Clean and deduplicate recipient emails
    recipients = list(set([e.strip() for e in to_emails if e and "@" in e]))
    if not recipients:
        logger.info("[Notification] No valid email addresses after cleaning.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🌾 AgroPredict: {subject}"
        msg["From"] = settings.SMTP_USER
        msg["To"] = ", ".join(recipients)

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        # Establish SMTP connection
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        server.ehlo()
        if settings.SMTP_PORT == 587:
            server.starttls()
            server.ehlo()

        if settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        server.sendmail(settings.SMTP_USER, recipients, msg.as_string())
        server.quit()

        logger.info(f"[Notification] Email sent successfully to {len(recipients)} recipient(s): {recipients}")
        return True
    except Exception as e:
        logger.error(f"[Notification] Error sending email via SMTP: {e}")
        return False


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
    slack_success = send_slack_notification(title, summary_text, details)

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

    email_success = send_email_notification(
        to_emails=user_emails,
        subject="Daily Market Data & Forecast Update",
        body_html=html_content,
        body_text=f"AgroPredict Daily Market Alert:\n\n{summary_text}\n\nVisit: {settings.FRONTEND_URL}"
    )

    return {
        "slack_sent": slack_success,
        "email_sent": email_success,
        "recipient_count": len(user_emails),
        "recipients": user_emails
    }

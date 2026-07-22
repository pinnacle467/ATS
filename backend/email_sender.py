"""Resend email sender helper.

Wraps the synchronous `resend` SDK in `asyncio.to_thread` so we don't block
the FastAPI event loop, and provides a small `send_email()` helper plus a
`build_reset_password_email()` template.
"""
import asyncio
import logging
import os
from typing import Optional

import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'Pinnacle ATS <onboarding@resend.dev>')
SENDER_REPLY_TO = os.environ.get('SENDER_REPLY_TO', '')

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """Send a transactional email via Resend. Runs sync SDK in a thread.

    Returns the Resend response dict (contains `id`). Raises on failure.
    """
    if not RESEND_API_KEY:
        raise RuntimeError('RESEND_API_KEY is not configured')

    params = {
        'from': SENDER_EMAIL,
        'to': [to],
        'subject': subject,
        'html': html,
    }
    if text:
        params['text'] = text
    rt = reply_to or SENDER_REPLY_TO
    if rt:
        params['reply_to'] = [rt] if isinstance(rt, str) else rt

    def _send():
        return resend.Emails.send(params)

    result = await asyncio.to_thread(_send)
    logger.info(f"Resend email sent to {to} — id={result.get('id')}")
    return result


def build_reset_password_email(user_name: str, reset_url: str, expires_minutes: int = 60) -> tuple[str, str]:
    """Return (html, plain_text) for a password-reset email."""
    safe_name = (user_name or 'there').split(' ')[0]
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Reset your Pinnacle ATS password</title></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f7f6;padding:40px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;border:1px solid #e5e7eb;overflow:hidden;">
          <tr>
            <td style="padding:28px 32px 0 32px;">
              <table cellspacing="0" cellpadding="0"><tr>
                <td style="width:40px;">
                  <div style="width:36px;height:36px;background:#10b981;border-radius:8px;color:#ffffff;text-align:center;line-height:36px;font-weight:700;font-size:18px;font-family:Georgia,serif;">P</div>
                </td>
                <td style="padding-left:12px;">
                  <div style="font-size:16px;font-weight:600;color:#0f172a;">Pinnacle ATS</div>
                  <div style="font-size:12px;color:#64748b;">Applicant Tracking System</div>
                </td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 0 32px;">
              <h1 style="margin:0 0 12px 0;font-size:22px;font-weight:600;color:#0f172a;">Reset your password</h1>
              <p style="margin:0 0 16px 0;font-size:15px;line-height:1.55;color:#334155;">Hi {safe_name}, we received a request to reset the password for your Pinnacle ATS account. Click the button below to choose a new password. This link will expire in <strong>{expires_minutes} minutes</strong>.</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:8px 32px 24px 32px;">
              <a href="{reset_url}" style="display:inline-block;background:#10b981;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 28px;border-radius:8px;">Reset password</a>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 16px 32px;">
              <p style="margin:0 0 8px 0;font-size:13px;color:#64748b;">Or copy and paste this URL into your browser:</p>
              <p style="margin:0;font-size:12px;color:#0f172a;word-break:break-all;background:#f1f5f9;padding:10px 12px;border-radius:6px;font-family:ui-monospace,Menlo,monospace;">{reset_url}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 28px 32px;border-top:1px solid #e5e7eb;">
              <p style="margin:16px 0 0 0;font-size:12px;line-height:1.55;color:#94a3b8;">If you didn't request this, you can safely ignore this email — your password won't change. For your security, this link can only be used once.</p>
              <p style="margin:12px 0 0 0;font-size:12px;color:#94a3b8;">© Pinnacle ATS</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    text = (
        f"Hi {safe_name},\n\n"
        f"We received a request to reset your Pinnacle ATS password.\n"
        f"Open this link within {expires_minutes} minutes to choose a new password:\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— Pinnacle ATS"
    )
    return html, text

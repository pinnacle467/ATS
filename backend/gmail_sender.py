"""Send transactional emails via Gmail API using a connected user's OAuth credentials."""
import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def send_gmail(creds: Credentials, to_email: str, subject: str, html_body: str) -> dict:
    msg = MIMEText(html_body, 'html')
    msg['to'] = to_email
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    return service.users().messages().send(userId='me', body={'raw': raw}).execute()

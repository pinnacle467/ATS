"""Send transactional emails via Gmail API using a connected user's OAuth credentials."""
import base64
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def send_gmail(creds: Credentials, to_email: str, subject: str, html_body: str, attachments=None) -> dict:
    """Send an HTML email, optionally with file attachments.

    `attachments` is a list of dicts: {'filename': str, 'data': bytes, 'content_type': str}.
    """
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(html_body, 'html'))
        for att in attachments:
            ctype = att.get('content_type') or 'application/octet-stream'
            maintype, _, subtype = ctype.partition('/')
            part = MIMEBase(maintype or 'application', subtype or 'octet-stream')
            part.set_payload(att['data'])
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=att.get('filename') or 'attachment')
            msg.attach(part)
    else:
        msg = MIMEText(html_body, 'html')
    msg['to'] = to_email
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    return service.users().messages().send(userId='me', body={'raw': raw}).execute()

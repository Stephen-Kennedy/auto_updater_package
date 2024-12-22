import smtplib
from email.mime.text import MIMEText


def send_email(from_email, to_email, smtp_server, email_password, subject, body, logger=None):
    """Send email notification."""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        with smtplib.SMTP(smtp_server, 587) as server:
            server.starttls()
            server.login(from_email, email_password)
            server.sendmail(from_email, [to_email], msg.as_string())
        
        if logger:
            logger.info(f"Email sent successfully: {subject}")
    except Exception as e:
        if logger:
            logger.error(f"Failed to send email: {e}")
        raise

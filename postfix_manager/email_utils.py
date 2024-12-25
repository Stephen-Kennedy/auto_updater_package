import smtplib
from email.mime.text import MIMEText
import socket

def send_email(from_email, to_email, smtp_server, email_password, subject, body, logger=None):
    """
    Send an email using SMTP.

    Args:
        from_email (str): Sender's email address.
        to_email (str): Recipient's email address.
        smtp_server (str): SMTP server address.
        email_password (str): Gmail application password (recommended).
        subject (str): Subject of the email.
        body (str): Body content of the email.
        logger (logging.Logger, optional): Logger for capturing log messages.

    Raises:
        Exception: Any exception raised during email sending.
    """
    try:
        # Add hostname to the email body
        hostname = socket.gethostname()
        full_body = f"{body}\n\nSent from hostname: {hostname}"
        full_subject = f"{hostname} server: {subject}"
        
        msg = MIMEText(full_body)
        msg['Subject'] = full_subject
        msg['From'] = from_email
        msg['To'] = to_email

        with smtplib.SMTP(smtp_server, 587) as server:
            server.starttls()  # Ensure a secure connection
            server.login(from_email, email_password)  # Use application password
            server.sendmail(from_email, [to_email], msg.as_string())

        if logger:
            logger.info(f"Email sent successfully to {to_email} with subject: {subject}")

    except smtplib.SMTPAuthenticationError as e:
        if logger:
            logger.error(f"Authentication error: {e}")
        raise ValueError(
            "Authentication failed. Check your email credentials (application password recommended).") from e
    except smtplib.SMTPException as e:
        if logger:
            logger.error(f"SMTP error occurred: {e}")
        raise
    except Exception as e:
        if logger:
            logger.error(f"An unexpected error occurred: {e}")
        raise

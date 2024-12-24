import smtplib
import socket
from email.mime.text import MIMEText


def send_email(from_email, to_email, smtp_server, email_password, subject, body, logger=None):
    """
    Send an email using SMTP, including the hostname in the subject.

    Args:
        from_email (str): Sender's email address.
        to_email (str): Recipient's email address.
        smtp_server (str): SMTP server address.
        email_password (str): Email application password (recommended).
        subject (str): Subject of the email.
        body (str): Body content of the email.
        logger (logging.Logger, optional): Logger for capturing log messages.

    Raises:
        Exception: Any exception raised during email sending.
    """
    try:
        # Append the hostname to the email subject
        hostname = socket.gethostname()
        full_subject = f"[{hostname}] {subject}"

        # Create the email message
        msg = MIMEText(body)
        msg['Subject'] = full_subject
        msg['From'] = from_email
        msg['To'] = to_email

        # Send the email using the SMTP server
        with smtplib.SMTP(smtp_server, 587) as server:
            server.starttls()  # Upgrade the connection to secure
            server.login(from_email, email_password)
            server.sendmail(from_email, [to_email], msg.as_string())

        if logger:
            logger.info(f"Email sent successfully to {to_email} with subject: {full_subject}")

    except smtplib.SMTPAuthenticationError as e:
        error_msg = "Authentication failed. Check your email credentials (application password recommended)."
        if logger:
            logger.error(f"{error_msg}: {e}")
        raise ValueError(error_msg) from e
    except smtplib.SMTPException as e:
        error_msg = "An SMTP error occurred while sending the email."
        if logger:
            logger.error(f"{error_msg}: {e}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = "An unexpected error occurred while sending the email."
        if logger:
            logger.error(f"{error_msg}: {e}")
        raise RuntimeError(error_msg) from e

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from models.config import Config
import smtplib


class Mail:

    def __init__(self):
        """

        """
        self.config = Config()
        self.host = self.config.get("MailHost")
        self.security = self.config.get("MailSecurity")
        self.port = self.config.get("MailPort")
        self.user = self.config.get("MailUser")
        self.receiver_address = self.config.get("MailReceiver")
        self.sender_address = self.config.get("MailSender")
        self.password = self.config.get("MailPassword")

    def send_mail(self, subject, message):
        """

        :param subject:
        :param message:
        :return:
        """
        if self.config.get("SendMail") == "1":
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_address
            msg['To'] = self.receiver_address
            # Record the MIME types of both parts - text/plain and text/html.
            part1 = MIMEText(message, 'plain')
            part2 = MIMEText(message, 'html')

            # Attach parts into message container.
            # According to RFC 2046, the last part of a multipart message, in this case
            # the HTML message, is best and preferred.
            msg.attach(part1)
            msg.attach(part2)
            server = smtplib.SMTP(self.host, self.port)
            server.login(self.user, self.password)
            server.sendmail(self.sender_address, [self.receiver_address], msg.as_string())
            server.quit()

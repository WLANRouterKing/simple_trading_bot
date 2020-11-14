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
        message = MIMEText(message)
        message['Subject'] = subject
        message['From'] = self.sender_address
        message['To'] = self.receiver_address

        server = smtplib.SMTP(self.host, self.port)
        server.login(self.user, self.password)
        server.sendmail(self.sender_address, [self.receiver_address], message.as_string())
        server.quit()

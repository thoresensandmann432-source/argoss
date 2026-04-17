import os
import unittest
from unittest.mock import patch


class SMTPMailerTests(unittest.TestCase):
    def test_status_uses_argos_email_fallback(self):
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "",
                "SMTP_PORT": "",
                "SMTP_USER": "",
                "SMTP_PASSWORD": "",
                "ARGOS_EMAIL_USERNAME": "argos@example.com",
                "ARGOS_EMAIL_PASSWORD": "secret",
                "ARGOS_EMAIL_SMTP_HOST": "smtp.example.com",
                "ARGOS_EMAIL_SMTP_PORT": "2525",
            },
            clear=False,
        ):
            from src.skills.smtp_mailer import SMTPMailer

            mailer = SMTPMailer()
            status = mailer.status()

            self.assertIn("argos@example.com", status)
            self.assertIn("smtp.example.com:2525", status)

    def test_email_test_command_requires_explicit_address(self):
        from src.skills.smtp_mailer import SMTPMailer

        mailer = SMTPMailer()
        result = mailer.handle_command("email тест")

        self.assertIn("email тест на <email>", result)

    def test_email_test_command_sends_predefined_message(self):
        with patch.dict(
            os.environ,
            {
                "SMTP_USER": "argos@example.com",
                "SMTP_PASSWORD": "secret",
                "SMTP_FROM": "argos@example.com",
            },
            clear=False,
        ):
            from src.skills.smtp_mailer import SMTPMailer

            mailer = SMTPMailer()
            with patch.object(mailer, "send", return_value="OK") as mock_send:
                result = mailer.handle_command("email тест на doppol85@gmail.com")

            self.assertEqual(result, "OK")
            mock_send.assert_called_once()
            args = mock_send.call_args.args
            self.assertEqual(args[0], "doppol85@gmail.com")
            self.assertEqual(args[1], "ARGOS SMTP test")
            self.assertIn("Это тестовое письмо от ARGOS", args[2])


if __name__ == "__main__":
    unittest.main()

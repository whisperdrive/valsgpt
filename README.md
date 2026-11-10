# Python Script App

Steps:

1. Install Python.

2. Set the SMTP credentials used to send mail (see [Configuration](#configuration)):
```
export SMTP_SENDER_EMAIL="you@gmail.com"
export SMTP_SENDER_PASSWORD="your-app-password"
```

3. Run the code to start the server:
```
python main.py
```

4. Access the URL on the browser:
```
http://localhost:5000/
```

## Configuration

The `/submit` route sends mail through Gmail SMTP (`smtp.gmail.com:587`). The
sender account is read from environment variables; nothing is hardcoded.

| Variable | Required | Description |
| --- | --- | --- |
| `SMTP_SENDER_EMAIL` | yes | Gmail address the mail is sent from. |
| `SMTP_SENDER_PASSWORD` | yes | Password for that account. With 2-Step Verification enabled, use a Google [App Password](https://myaccount.google.com/apppasswords), not the account password. |

If either variable is missing or empty, `/submit` responds with HTTP 500 and a
message naming the missing variable(s), and no mail is sent.

On Windows (PowerShell) use `$env:SMTP_SENDER_EMAIL = "..."` instead of `export`.

Never commit these values to the repository. Set them in your shell, your
process manager, or your hosting provider's secret settings.

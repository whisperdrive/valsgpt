
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from app import app
from flask import render_template, request, redirect	
from waitress import serve

SMTP_SENDER_EMAIL_VAR = "SMTP_SENDER_EMAIL"
SMTP_SENDER_PASSWORD_VAR = "SMTP_SENDER_PASSWORD"

class MissingSMTPCredentialsError(RuntimeError):
	pass

def get_smtp_credentials():
	"""Read the sender address and password from the environment."""
	sender_email = os.environ.get(SMTP_SENDER_EMAIL_VAR, "").strip()
	sender_password = os.environ.get(SMTP_SENDER_PASSWORD_VAR, "").strip()
	missing = [name for name, value in (
		(SMTP_SENDER_EMAIL_VAR, sender_email),
		(SMTP_SENDER_PASSWORD_VAR, sender_password),
	) if not value]
	if missing:
		raise MissingSMTPCredentialsError(
			"Cannot send email: missing required environment variable(s): "
			+ ", ".join(missing)
			+ ". See README.md for setup instructions."
		)
	return sender_email, sender_password

@app.route('/')
def main():
	return render_template("userInput.html")
# def Web_App(environment, response):
# 	status='200 OK'
# 	headers=[('content-type','text/html; charset=utf-8')]
# 	response(status,headers)
# 	fname = "templates/userInput.html"
# 	html_file = open(fname, 'r', encoding='utf-8')
# 	source_code = html_file.read() 
# 	print(response)
# 	return [bytes(source_code, 'utf8')]

@app.route('/submit', methods=['POST'])
def submit_data():
	try:
		_name = request.form["name"]
		_businessDescription = request.form["businessDescription"]
		_screeningCriteria = request.form["screeningCriteria"]
		_email = request.form["email"]

		# validate the received values
		if _name and _email and _businessDescription and _screeningCriteria and request.method == 'POST':
			# Data to be written to the text file
			_stringForData = "Business Description: " + _businessDescription + "\n" + "Screening Criteria: " + _screeningCriteria 
			# Specify the file path and open the file in write mode
			file_path = "output.txt"
			with open(file_path, "w") as file:
				# Write the data to the file
				file.write(_stringForData)

			# Sender address and password come from the environment
			# (use an App Password if you have 2FA enabled)
			sender_email, sender_password = get_smtp_credentials()
			recipient_email = _email

			# Create the message
			msg = MIMEMultipart()
			msg["From"] = _name + " <" + sender_email + ">"
			msg["To"] = recipient_email
			msg["Subject"] = "Hello!" + "\n" +"I will attach the text here." + "\n" + "please check it."

			# Attach the text file
			attachment = open(file_path, "rb")
			part = MIMEBase("application", "octet-stream")
			part.set_payload(attachment.read())
			encoders.encode_base64(part)
			part.add_header("Content-Disposition", f"attachment; filename= {file_path}")
			msg.attach(part)
			# Send the email
			server = smtplib.SMTP("smtp.gmail.com", 587)
			server.starttls()
			server.login(sender_email, sender_password)
			text = msg.as_string()
			server.sendmail(sender_email, recipient_email, text)
			server.quit()
			print("Email sent successfully!")

			# Inform that the operation is complete
			return redirect('/welcome')
			print(f"Data has been written to '{file_path}'")
		else:
			return 'Error while submiting the input information'

	except MissingSMTPCredentialsError as e:
		print(e)
		return str(e), 500

	except Exception as e:
		print(e)

	finally:
		print("The 'try except' is finished")
@app.route('/welcome')
def welcome():
	return render_template('welcome.html')

def create_app():
   return app

if __name__ == "__main__":
  app.run()

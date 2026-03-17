import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

def send_sms(to_number, message_body):
    """
    Sends an SMS using Twilio.
    Returns the message SID if successful, None otherwise.
    """
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')

    if not all([account_sid, auth_token, from_number]):
        print("⚠️  Twilio credentials missing. SMS not sent.")
        return None

    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=to_number
        )
        print(f"✅ SMS sent successfully! SID: {message.sid}")
        return message.sid
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return None

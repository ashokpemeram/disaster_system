from datetime import datetime, timedelta
import os

from openai import OpenAI

from db import alert_collection
from tools.sms_tool import send_sms

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY"),
)


class AlertAgent:
    def run(self, risk_assessment):
        if risk_assessment["overall_risk"] == "low":
            return {"message": "No alert needed"}

        area_id = risk_assessment.get("areaId")
        location = risk_assessment.get("location", "Unknown")
        dedupe_query = {"area_id": area_id} if area_id else {"location": location}

        try:
            last_alert = alert_collection.find_one(
                dedupe_query,
                sort=[("timestamp", -1)],
            )
        except Exception as e:
            last_alert = None
            print(f"DB lookup failed (alert dedupe): {e}")

        if last_alert:
            last_time = last_alert.get("timestamp")
            if (
                last_alert.get("risk_level") == risk_assessment["overall_risk"]
                and last_time
                and (datetime.utcnow() - last_time) < timedelta(minutes=5)
            ):
                print(
                    f"Recent alert already exists for {location}. Skipping duplicate alert and SMS."
                )
                last_alert.setdefault(
                    "sms_status",
                    {
                        "status": "skipped",
                        "detail": "A matching alert already exists within the 5-minute dedupe window.",
                        "recipient": os.getenv("RECIPIENT_PHONE_NUMBER"),
                    },
                )
                return last_alert

        alert_message = (
            "Urgent: Disaster risk detected in your area. Please stay tuned for updates."
        )

        try:
            prompt = f"""
            Generate a short, urgent public disaster alert message for:
            {risk_assessment}
            Keep it under 160 characters for SMS compatibility.
            """

            response = client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                extra_headers={
                    "HTTP-Referer": "https://cerca-app.com",
                    "X-Title": "CERCA Disaster System",
                },
            )

            alert_message = response.choices[0].message.content
            print("Alert Agent (AI):", alert_message)
        except Exception as e:
            print(f"AI alert generation failed: {e}. Using fallback message.")

        recipient = os.getenv("RECIPIENT_PHONE_NUMBER")
        sms_status = {
            "status": "not_attempted",
            "detail": "SMS was not attempted.",
            "recipient": recipient,
        }
        if recipient:
            try:
                send_sms(recipient, alert_message)
                sms_status = {
                    "status": "sent",
                    "detail": f"SMS alert sent successfully to {recipient}.",
                    "recipient": recipient,
                }
            except Exception as sms_error:
                print(f"SMS delivery failed: {sms_error}")
                sms_status = {
                    "status": "failed",
                    "detail": f"SMS delivery failed: {sms_error}",
                    "recipient": recipient,
                }
        else:
            print("RECIPIENT_PHONE_NUMBER missing. Skipping SMS.")
            sms_status = {
                "status": "skipped",
                "detail": "RECIPIENT_PHONE_NUMBER is not configured. SMS was skipped.",
                "recipient": None,
            }

        alert_doc = {
            "location": location,
            "area_id": area_id,
            "risk_level": risk_assessment["overall_risk"],
            "alert_message": alert_message,
            "sms_status": sms_status,
            "timestamp": datetime.utcnow(),
            "risk": risk_assessment,
        }

        try:
            alert_collection.insert_one(alert_doc)
            print(f"Alert stored for {alert_doc['location']}.")
        except Exception as e:
            print(f"DB operation failed (alert): {e}")

        return alert_doc

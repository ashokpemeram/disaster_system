from db import alert_collection
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class AlertAgent:

    def run(self, risk_assessment):
        if risk_assessment["overall_risk"] == "low":
            return {"message": "No alert needed"}

        prompt = f"""
        Generate a public disaster alert message for:
        {risk_assessment}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        alert_message = response.choices[0].message.content
        print("Alert Agent:",alert_message)

        alert_doc = {
            "location": risk_assessment["location"],
            "risk_level": risk_assessment["overall_risk"],
            "alert_message": alert_message
        }

        try:
            alert_collection.insert_one(alert_doc)
        except Exception as e:
            print(f"⚠️  DB insert skipped (alert): {e}")
        return alert_doc
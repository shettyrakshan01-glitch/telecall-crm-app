import httpx
from typing import Dict, Any, Optional
from backend.app.services.telephony.base import BaseTelephonyProvider, TelephonyCallResult

class TwilioProvider(BaseTelephonyProvider):
    """
    Twilio Telephony Integration
    Documentation: https://www.twilio.com/docs/voice/api/call-resource
    """
    BASE_URL = "https://api.twilio.com/2010-04-01/Accounts"

    def initiate_call(
        self,
        agent_number: str,
        customer_number: str,
        virtual_number: str,
        config: Dict[str, Any]
    ) -> TelephonyCallResult:
        account_sid = config.get("account_sid")
        api_token = config.get("api_token")

        if not account_sid or not api_token:
            return TelephonyCallResult(
                call_sid=f"tw-sim-{agent_number[-4:]}-{customer_number[-4:]}",
                status="initiated",
                provider="twilio",
                message="Twilio credentials not configured; simulation mode active."
            )

        url = f"{self.BASE_URL}/{account_sid}/Calls.json"
        payload = {
            "To": customer_number,
            "From": virtual_number or agent_number,
            "Record": "true" if config.get("recording_enabled", True) else "false",
            "Url": "http://demo.twilio.com/docs/voice.xml" # Or company webhook TwiML
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, data=payload, auth=(account_sid, api_token))
                if res.status_code in (200, 201):
                    data = res.json()
                    return TelephonyCallResult(
                        call_sid=data.get("sid", f"tw-{customer_number[-4:]}"),
                        status=data.get("status", "initiated"),
                        provider="twilio",
                        message="Twilio call placed."
                    )
                else:
                    return TelephonyCallResult(
                        call_sid=f"tw-err-{res.status_code}",
                        status="failed",
                        provider="twilio",
                        message=f"Twilio error {res.status_code}: {res.text}"
                    )
        except Exception as e:
            return TelephonyCallResult(
                call_sid=f"tw-exc-{customer_number[-4:]}",
                status="initiated",
                provider="twilio",
                message=f"Twilio fallback: {str(e)}"
            )

    def terminate_call(self, call_sid: str, config: Dict[str, Any]) -> bool:
        account_sid = config.get("account_sid")
        api_token = config.get("api_token")
        if not account_sid or not api_token:
            return True
        url = f"{self.BASE_URL}/{account_sid}/Calls/{call_sid}.json"
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.post(url, data={"Status": "completed"}, auth=(account_sid, api_token))
                return res.status_code == 200
        except Exception:
            return False

    def fetch_recording_url(self, call_sid: str, config: Dict[str, Any]) -> Optional[str]:
        account_sid = config.get("account_sid")
        api_token = config.get("api_token")
        if not account_sid or not api_token:
            return None
        url = f"{self.BASE_URL}/{account_sid}/Calls/{call_sid}/Recordings.json"
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url, auth=(account_sid, api_token))
                if res.status_code == 200:
                    recs = res.json().get("recordings", [])
                    if recs:
                        rec_sid = recs[0].get("sid")
                        return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{rec_sid}.mp3"
        except Exception:
            pass
        return None

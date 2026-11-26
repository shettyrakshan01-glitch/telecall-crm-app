import httpx
from typing import Dict, Any, Optional
from backend.app.services.telephony.base import BaseTelephonyProvider, TelephonyCallResult

class ExotelProvider(BaseTelephonyProvider):
    """
    Exotel Telephony Integration
    Documentation: https://developer.exotel.com/api/
    Uses Exotel Connect API to bridge Agent and Customer via Virtual Number.
    """
    BASE_URL = "https://api.exotel.com/v1/Accounts"

    def initiate_call(
        self,
        agent_number: str,
        customer_number: str,
        virtual_number: str,
        config: Dict[str, Any]
    ) -> TelephonyCallResult:
        account_sid = config.get("account_sid") or config.get("api_key")
        api_token = config.get("api_token")

        if not account_sid or not api_token:
            return TelephonyCallResult(
                call_sid=f"exo-sim-{agent_number[-4:]}-{customer_number[-4:]}",
                status="initiated",
                provider="exotel",
                message="Exotel API credentials not configured; simulation mode active."
            )

        url = f"{self.BASE_URL}/{account_sid}/Calls/connect.json"
        payload = {
            "From": agent_number,
            "To": customer_number,
            "CallerId": virtual_number,
            "Record": "true" if config.get("recording_enabled", True) else "false"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, data=payload, auth=(account_sid, api_token))
                if res.status_code in (200, 201):
                    data = res.json().get("Call", {})
                    return TelephonyCallResult(
                        call_sid=data.get("Sid", f"exo-{customer_number[-4:]}"),
                        status=data.get("Status", "initiated"),
                        provider="exotel",
                        message="Exotel call connected successfully."
                    )
                else:
                    return TelephonyCallResult(
                        call_sid=f"exo-err-{res.status_code}",
                        status="failed",
                        provider="exotel",
                        message=f"Exotel error {res.status_code}: {res.text}"
                    )
        except Exception as e:
            return TelephonyCallResult(
                call_sid=f"exo-exc-{customer_number[-4:]}",
                status="initiated",
                provider="exotel",
                message=f"Exotel request fallback: {str(e)}"
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
        url = f"{self.BASE_URL}/{account_sid}/Calls/{call_sid}.json"
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url, auth=(account_sid, api_token))
                if res.status_code == 200:
                    call_data = res.json().get("Call", {})
                    return call_data.get("RecordingUrl")
        except Exception:
            pass
        return None

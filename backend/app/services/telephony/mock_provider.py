import uuid
import time
from typing import Dict, Any, Optional
from backend.app.services.telephony.base import BaseTelephonyProvider, TelephonyCallResult

class MockTelephonyProvider(BaseTelephonyProvider):
    def initiate_call(
        self,
        agent_number: str,
        customer_number: str,
        virtual_number: str,
        config: Dict[str, Any]
    ) -> TelephonyCallResult:
        sid = f"mock-call-{uuid.uuid4().hex[:12]}"
        return TelephonyCallResult(
            call_sid=sid,
            status="connected",
            provider="mock",
            message=f"Simulated call placed from {agent_number} to {customer_number} via {virtual_number or 'Virtual Number'}"
        )

    def terminate_call(self, call_sid: str, config: Dict[str, Any]) -> bool:
        return True

    def fetch_recording_url(self, call_sid: str, config: Dict[str, Any]) -> Optional[str]:
        return None

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class TelephonyCallResult:
    def __init__(
        self,
        call_sid: str,
        status: str, # initiated, ringing, failed
        provider: str,
        message: Optional[str] = None
    ):
        self.call_sid = call_sid
        self.status = status
        self.provider = provider
        self.message = message

class BaseTelephonyProvider(ABC):
    @abstractmethod
    def initiate_call(
        self,
        agent_number: str,
        customer_number: str,
        virtual_number: str,
        config: Dict[str, Any]
    ) -> TelephonyCallResult:
        """
        Initiates a click-to-call session between agent and customer via the virtual number.
        """
        pass

    @abstractmethod
    def terminate_call(self, call_sid: str, config: Dict[str, Any]) -> bool:
        """
        Terminates an ongoing call session.
        """
        pass

    @abstractmethod
    def fetch_recording_url(self, call_sid: str, config: Dict[str, Any]) -> Optional[str]:
        """
        Retrieves the recording audio URL from the telephony provider.
        """
        pass

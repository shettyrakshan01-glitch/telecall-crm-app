from typing import Dict, Any
from backend.app.services.telephony.base import BaseTelephonyProvider
from backend.app.services.telephony.mock_provider import MockTelephonyProvider
from backend.app.services.telephony.exotel import ExotelProvider
from backend.app.services.telephony.twilio_provider import TwilioProvider
from backend.app.services.telephony.other_providers import OzonetelProvider, KnowlarityProvider, MyOperatorProvider

class TelephonyFactory:
    _providers = {
        "mock": MockTelephonyProvider(),
        "exotel": ExotelProvider(),
        "twilio": TwilioProvider(),
        "ozonetel": OzonetelProvider(),
        "knowlarity": KnowlarityProvider(),
        "myoperator": MyOperatorProvider()
    }

    @classmethod
    def get_provider(cls, provider_name: str) -> BaseTelephonyProvider:
        name = (provider_name or "mock").lower().strip()
        if name in cls._providers:
            return cls._providers[name]
        return cls._providers["mock"]

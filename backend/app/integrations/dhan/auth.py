import logging
from datetime import datetime, timedelta

# import pyotp
from dhanhq import DhanLogin

from app.config import settings

logger = logging.getLogger(__name__)


class DhanAuth:
    def __init__(self):
        self.client_id = settings.dhan_client_id
        self.app_id = settings.dhan_app_id
        self.app_secret = settings.dhan_app_secret
        self.pin = settings.dhan_pin
        self.totp_secret = settings.dhan_totp_secret

        self.access_token = None
        self.expires_at = None

    def _is_token_valid(self):
        if not self.access_token or not self.expires_at:
            return False

        # Refresh 5 minutes before expiry
        return datetime.utcnow() < (
            self.expires_at - timedelta(minutes=5)
        )

    def generate_token(self):
        """
        Generate a new Dhan access token using Dhan SDK.
        """

        if not self.client_id:
            raise RuntimeError("DHAN_CLIENT_ID is not configured")

        if not self.app_id:
            raise RuntimeError("DHAN_APP_ID is not configured")

        if not self.app_secret:
            raise RuntimeError("DHAN_APP_SECRET is not configured")

        if not self.pin:
            raise RuntimeError("DHAN_PIN is not configured")

        if not self.totp_secret:
            raise RuntimeError("DHAN_TOTP_SECRET is not configured")

        try:
            dhan_login = DhanLogin(
                self.client_id
            )

            # Generate current TOTP
            totp = pyotp.TOTP(
                self.totp_secret
            ).now()

            response = dhan_login.generate_token(
                self.pin,
                totp
            )

            token = response.get("accessToken")

            if not token:
                raise RuntimeError(
                    f"Dhan did not return access token: {response}"
                )

            self.access_token = token

            # Dhan access token validity = 24 hours
            self.expires_at = (
                datetime.utcnow()
                + timedelta(hours=24)
            )

            logger.info(
                "Dhan access token generated successfully"
            )

            return self.access_token

        except Exception as exc:
            logger.exception(
                "Failed to generate Dhan access token"
            )
            raise RuntimeError(
                f"Dhan authentication failed: {exc}"
            ) from exc

    def get_access_token(self):
        """
        Return current token or generate a new one
        when the existing token is expired/near expiry.
        """

        if self._is_token_valid():
            return self.access_token

        return self.generate_token()


dhan_auth = DhanAuth()


def get_access_token():
    return dhan_auth.get_access_token()
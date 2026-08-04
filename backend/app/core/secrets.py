import keyring
from keyring.errors import KeyringError


class SecretStore:
    service = "cortex"

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(self.service, name)
        except KeyringError:
            # Containers normally have no OS credential-store backend. Callers
            # fall back to their development/Docker environment variables.
            return None

    def set(self, name: str, value: str) -> None:
        keyring.set_password(self.service, name, value)


def redact(value: str | None) -> str:
    return "[REDACTED]" if value else ""

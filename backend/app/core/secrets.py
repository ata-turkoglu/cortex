import keyring


class SecretStore:
    service = "cortex"

    def get(self, name: str) -> str | None:
        return keyring.get_password(self.service, name)

    def set(self, name: str, value: str) -> None:
        keyring.set_password(self.service, name, value)


def redact(value: str | None) -> str:
    return "[REDACTED]" if value else ""

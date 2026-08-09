import contextlib
import json
import os
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.errors import KeyringError


class SecretStoreUnavailable(RuntimeError):
    """Raised when a persistent OS credential store is unavailable."""


class SecretStore:
    service = "cortex"

    @property
    def _directory(self) -> Path:
        return Path(os.getenv("CORTEX_SECRET_STORE_PATH", "./data/secrets"))

    @property
    def _key_path(self) -> Path:
        return self._directory / "master.key"

    @property
    def _values_path(self) -> Path:
        return self._directory / "values.json"

    def _cipher(self) -> Fernet:
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._key_path.exists():
            key = self._key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            self._key_path.write_bytes(key)
            with contextlib.suppress(OSError):
                os.chmod(self._key_path, 0o600)
        return Fernet(key)

    def _read_values(self) -> dict[str, str]:
        if not self._values_path.exists():
            return {}
        try:
            raw = json.loads(self._values_path.read_text(encoding="utf-8"))
            return {
                name: self._cipher().decrypt(value.encode("ascii")).decode("utf-8")
                for name, value in raw.items()
            }
        except (OSError, ValueError, TypeError, InvalidToken) as exc:
            raise SecretStoreUnavailable("The Docker secret store could not be read.") from exc

    def _write_value(self, name: str, value: str) -> None:
        values = self._read_values()
        encrypted = self._cipher().encrypt(value.encode("utf-8")).decode("ascii")
        current = {
            key: self._cipher().encrypt(secret.encode("utf-8")).decode("ascii")
            for key, secret in values.items()
        }
        current[name] = encrypted
        temporary = self._values_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(temporary, 0o600)
        temporary.replace(self._values_path)

    def get(self, name: str) -> str | None:
        try:
            value = keyring.get_password(self.service, name)
            if value:
                return value
        except KeyringError:
            pass
        return self._read_values().get(name)

    def set(self, name: str, value: str) -> None:
        try:
            keyring.set_password(self.service, name, value)
        except KeyringError:
            self._write_value(name, value)


def redact(value: str | None) -> str:
    return "[REDACTED]" if value else ""

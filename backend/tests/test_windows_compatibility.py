from app.core.config import Settings
from app.core.paths import normalized_data_path


def test_windows_style_turkish_workspace_path_stays_within_data_root(tmp_path):
    data_root = tmp_path / "Cortex Veri"
    candidate = data_root / "çalışma alanı" / "İçerik.pdf"
    resolved = normalized_data_path(str(candidate), data_root)
    assert resolved == candidate.resolve()


def test_cortex_owned_ollama_loopback_is_the_default():
    assert Settings(_env_file=None).ollama_base_url == "http://127.0.0.1:11434"

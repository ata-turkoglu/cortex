from pathlib import Path

import pytest

from app.core.paths import normalized_data_path


def test_path_cannot_escape_data_root(tmp_path: Path):
    with pytest.raises(ValueError):
        normalized_data_path(str(tmp_path.parent), tmp_path)

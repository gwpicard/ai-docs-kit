import pytest
from PIL import Image

from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.compose import ComposeError, compose


@pytest.mark.parametrize("escape", ["../secret.png", "absolute"])
def test_image_outside_the_assets_folder_is_refused(tmp_path, escape):
    assets = tmp_path / "assets"
    assets.mkdir()
    secret = tmp_path / "secret.png"
    Image.new("RGB", (10, 10)).save(secret)
    image = str(secret) if escape == "absolute" else escape
    section = Section(id="s", intent="full-image", component="full-image", title="t", image=image)
    doc = Document(front={}, format="slides", sections=[section])
    with pytest.raises(ComposeError):
        compose(doc, assets=[assets])

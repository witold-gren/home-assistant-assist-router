"""Brand images shipped with the integration (Home Assistant 2026.3+ local brands)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

BRAND = Path(__file__).parents[1] / "custom_components" / "assist_router" / "brand"


@pytest.mark.parametrize("name", ["icon", "dark_icon", "logo", "dark_logo"])
def test_brand_image_and_retina_variant(name: str) -> None:
    image = Image.open(BRAND / f"{name}.png")
    retina = Image.open(BRAND / f"{name}@2x.png")
    assert image.height == 256
    assert retina.size == (image.width * 2, image.height * 2)
    if name.endswith("icon"):
        assert image.width == 256

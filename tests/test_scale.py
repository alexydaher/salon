# SPDX-License-Identifier: GPL-3.0-or-later
from salon.ui.scale import Scale


def test_scale_carries_the_configured_safe_area() -> None:
    scale = Scale(1080).with_safe_area(7.5)
    assert scale.safe_margin == 81.0
    assert scale.safe_margin_px == 81


def test_safe_area_scales_with_the_viewport() -> None:
    assert Scale(2160, 4.5).safe_margin_px == 972 // 10

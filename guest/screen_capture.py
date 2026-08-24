"""
DXGI & Multi-Backend Screen Capture Engine for Isolated Computer-Use VM.
Provides low-latency framebuffer capture, Region-of-Interest (ROI) cropping,
coordinate grid annotations for vision agents, and visual diff analysis.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw


class ScreenCaptureEngine:
    """High-performance screen capture and visual analysis engine."""

    def __init__(self, default_width: int = 1920, default_height: int = 1080):
        self.default_width = default_width
        self.default_height = default_height
        self._backend = "mss"
        self._sct = None
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize the fastest available capture backend."""
        try:
            import mss  # type: ignore
            self._sct = mss.mss()
            self._backend = "mss"
        except Exception:
            # Fallback to PIL ImageGrab if mss is not installed
            self._backend = "pil"

    def capture_frame(
        self,
        region: Optional[Union[Tuple[int, int, int, int], List[int]]] = None,
        annotate_grid: bool = False,
        grid_interval: int = 100,
    ) -> Image.Image:
        """
        Capture the current virtual desktop frame.

        :param region: Optional [x, y, width, height] crop rectangle.
        :param annotate_grid: If True, overlays a labeled coordinate grid on the image.
        :param grid_interval: Spacing between grid lines in pixels.
        :return: PIL.Image in RGB mode.
        """
        if self._backend == "mss" and self._sct is not None:
            # Monitor 1 is primary display
            if len(self._sct.monitors) > 1:
                mon = self._sct.monitors[1]
            else:
                mon = self._sct.monitors[0]

            if region:
                rx, ry, rw, rh = region
                grab_rect = {"top": ry, "left": rx, "width": rw, "height": rh}
            else:
                grab_rect = mon

            raw_frame = self._sct.grab(grab_rect)
            img = Image.frombytes("RGB", raw_frame.size, raw_frame.bgra, "raw", "BGRX")
        else:
            from PIL import ImageGrab
            if region:
                rx, ry, rw, rh = region
                bbox = (rx, ry, rx + rw, ry + rh)
            else:
                bbox = (0, 0, self.default_width, self.default_height)
            img = ImageGrab.grab(bbox=bbox)

        if annotate_grid:
            img = self.draw_coordinate_grid(img, interval=grid_interval)

        return img

    def capture_bytes(
        self,
        region: Optional[Union[Tuple[int, int, int, int], List[int]]] = None,
        format: str = "png",
        quality: int = 85,
        annotate_grid: bool = False,
    ) -> Tuple[bytes, str]:
        """
        Captures frame and serializes directly to compressed bytes.

        :return: (image_bytes, mime_type)
        """
        img = self.capture_frame(region=region, annotate_grid=annotate_grid)
        buf = io.BytesIO()

        fmt_upper = format.upper()
        if fmt_upper in ("JPEG", "JPG"):
            img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        elif fmt_upper == "WEBP":
            img.save(buf, format="WEBP", quality=quality)
            mime = "image/webp"
        else:
            img.save(buf, format="PNG", optimize=False)
            mime = "image/png"

        return buf.getvalue(), mime

    @staticmethod
    def draw_coordinate_grid(
        img: Image.Image,
        interval: int = 100,
        line_color: Tuple[int, int, int, int] = (255, 0, 0, 120),
        text_color: Tuple[int, int, int] = (255, 255, 0),
    ) -> Image.Image:
        """
        Overlays coordinate grid and axis labels onto image for LLM spatial reasoning.
        """
        overlay = img.convert("RGBA")
        draw = ImageDraw.Draw(overlay)
        w, h = overlay.size

        # Vertical lines & X labels
        for x in range(0, w, interval):
            draw.line([(x, 0), (x, h)], fill=line_color, width=1)
            draw.text((x + 2, 2), f"{x}", fill=text_color)
            if h > 200:
                draw.text((x + 2, h - 15), f"{x}", fill=text_color)

        # Horizontal lines & Y labels
        for y in range(0, h, interval):
            draw.line([(0, y), (w, y)], fill=line_color, width=1)
            draw.text((2, y + 2), f"{y}", fill=text_color)
            if w > 200:
                draw.text((w - 35, y + 2), f"{y}", fill=text_color)

        return overlay.convert("RGB")

    @staticmethod
    def compare_images(
        current_img: Image.Image,
        baseline_img: Image.Image,
        threshold: float = 0.05,
    ) -> Dict[str, Union[bool, float, Optional[List[int]], Image.Image]]:
        """
        Compares current frame against baseline reference image.
        Returns similarity score (0.0 to 1.0), match boolean, and diff heatmap.
        """
        # Ensure identical dimensions
        if current_img.size != baseline_img.size:
            baseline_img = baseline_img.resize(current_img.size, Image.Resampling.BILINEAR)

        arr1 = np.array(current_img.convert("RGB"), dtype=np.float32)
        arr2 = np.array(baseline_img.convert("RGB"), dtype=np.float32)

        # Compute normalized absolute pixel difference
        abs_diff = np.abs(arr1 - arr2) / 255.0
        pixel_diff = np.mean(abs_diff, axis=2)  # 2D difference map

        mismatch_mask = pixel_diff > threshold
        mismatch_ratio = float(np.sum(mismatch_mask)) / float(pixel_diff.size)
        similarity = 1.0 - mismatch_ratio

        # Generate visual difference heatmap
        heatmap_arr = np.zeros((*pixel_diff.shape, 3), dtype=np.uint8)
        heatmap_arr[..., 0] = (pixel_diff * 255).astype(np.uint8)  # Red channel shows difference
        heatmap_img = Image.fromarray(heatmap_arr)

        return {
            "match": bool(similarity >= (1.0 - threshold)),
            "similarity": round(similarity, 4),
            "mismatch_ratio": round(mismatch_ratio, 4),
            "heatmap": heatmap_img,
        }


# Quick CLI verification
if __name__ == "__main__":
    engine = ScreenCaptureEngine()
    print("Capturing frame...")
    img = engine.capture_frame(annotate_grid=True)
    print(f"Captured {img.size} image successfully. Backend: {engine._backend}")

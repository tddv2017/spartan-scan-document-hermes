"""Image Preprocessing Engine for Hermes CMS Screen Vision.

Optimizes raster desktop screenshots for character recognition via 2x Bicubic upscaling,
grayscale luminance extraction, adaptive contrast enhancement (CLAHE), and edge sharpening.
"""

from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image

from app.core.config import PREPROCESS_SCALE_FACTOR


class ImagePreprocessor:
    """Preprocesses desktop screenshots to maximize OCR accuracy on Hermes CMS interfaces."""

    def __init__(
        self,
        scale_factor: float = PREPROCESS_SCALE_FACTOR,
        clahe_clip_limit: float = 2.0,
        clahe_tile_grid_size: int = 8,
        apply_sharpening: bool = True,
    ) -> None:
        self.scale_factor = scale_factor
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_tile_grid_size = clahe_tile_grid_size
        self.apply_sharpening = apply_sharpening

    def to_cv2_image(self, image: Union[Image.Image, np.ndarray, str, Path]) -> np.ndarray:
        """Converts any supported image representation (PIL Image, path, array) to a NumPy BGR array."""
        if isinstance(image, (str, Path)):
            path_str = str(image)
            img = cv2.imread(path_str)
            if img is None:
                raise ValueError(f"Could not load image from path: {path_str}")
            return img

        if isinstance(image, Image.Image):
            # Convert PIL RGB to OpenCV BGR
            rgb_arr = np.array(image.convert("RGB"))
            return cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)

        if isinstance(image, np.ndarray):
            if image.ndim == 2:
                # Grayscale to BGR
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if image.ndim == 3:
                return image.copy()

        raise TypeError(f"Unsupported image type: {type(image)}")

    def scale_bicubic(self, image: np.ndarray, factor: Optional[float] = None) -> np.ndarray:
        """Upscale image using Bicubic interpolation to expand character stroke pixels."""
        f = factor or self.scale_factor
        if abs(f - 1.0) < 1e-3:
            return image

        return cv2.resize(image, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)

    def to_grayscale(self, image: np.ndarray) -> np.ndarray:
        """Convert BGR/RGB array to single-channel 8-bit grayscale."""
        if image.ndim == 2:
            return image
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def enhance_contrast(self, gray_image: np.ndarray) -> np.ndarray:
        """Apply Contrast Limited Adaptive Histogram Equalization (CLAHE).

        Improves contrast between light gray Hermes CMS backgrounds and dark text glyphs.
        """
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=(self.clahe_tile_grid_size, self.clahe_tile_grid_size),
        )
        return clahe.apply(gray_image)

    def sharpen_edges(self, gray_image: np.ndarray, strength: float = 1.2) -> np.ndarray:
        """Unsharp masking to enhance character boundary definitions."""
        blurred = cv2.GaussianBlur(gray_image, (0, 0), sigmaX=1.0)
        sharpened = cv2.addWeighted(gray_image, 1.0 + strength, blurred, -strength, 0)
        return sharpened

    def preprocess(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        return_bgr: bool = True,
    ) -> np.ndarray:
        """Full preprocessing pipeline:

        1. Convert to OpenCV BGR array
        2. 2.0x Bicubic upscaling
        3. Grayscale luminance conversion
        4. CLAHE contrast enhancement
        5. Edge sharpening
        6. Return 3-channel BGR (for RapidOCR) or 1-channel Grayscale.
        """
        bgr = self.to_cv2_image(image)

        # Stage 1: Bicubic 2x upscaling
        scaled = self.scale_bicubic(bgr)

        # Stage 2: Grayscale conversion
        gray = self.to_grayscale(scaled)

        # Stage 3: Adaptive contrast
        enhanced = self.enhance_contrast(gray)

        # Stage 4: Optional sharpening
        if self.apply_sharpening:
            enhanced = self.sharpen_edges(enhanced)

        # RapidOCR expects a 3-channel BGR/RGB array or single-channel
        if return_bgr:
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        return enhanced

    def preprocess_pil(self, image: Union[Image.Image, np.ndarray, str, Path]) -> Image.Image:
        """Preprocess and return result as PIL Image."""
        bgr = self.preprocess(image, return_bgr=True)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

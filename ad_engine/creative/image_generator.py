"""Image generation for ad creatives (v2). Never raises; returns None on any failure."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Optional: use google-genai for Imagen. If not installed or API fails, we return None.
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


def _build_image_prompt(brief: dict, ad_copy: dict) -> str:
    """Build a short, brand-safe prompt for image generation."""
    product = brief.get("product", "product")
    audience = brief.get("audience", "audience")
    headline = ad_copy.get("headline") or ad_copy.get("primary_text", "")[:80]
    # Keep it generic and safe for Imagen (no people/faces unless needed)
    return (
        f"Professional advertising image for {product}, targeting {audience}. "
        f"Clean, modern, suitable for social media. No text overlay. "
        f"Concept: {headline}"
    ).strip()


def _save_image_from_genai(response: Any, path: Path) -> bool:
    """Save first generated image from google.genai response to path. Returns True on success."""
    try:
        if not hasattr(response, "generated_images") or not response.generated_images:
            return False
        img = response.generated_images[0]
        if hasattr(img, "image"):
            data = img.image
            if hasattr(data, "save"):
                data.save(path)
                return True
            if hasattr(data, "_pil_image"):
                data._pil_image.save(path)
                return True
            # Bytes
            if isinstance(data, bytes):
                path.write_bytes(data)
                return True
        return False
    except Exception as e:
        logger.warning("Failed to save generated image: %s", e)
        return False


class ImageGenerator:
    """Generate creative images for ads. Never raises; returns None when generation fails."""

    def __init__(
        self,
        model: str = "imagen-3.0-generate-001",
        use_placeholder_on_failure: bool = False,
    ):
        self.model = model
        self.use_placeholder_on_failure = use_placeholder_on_failure
        self._client = None
        if _GENAI_AVAILABLE:
            try:
                self._client = genai.Client()
            except Exception as e:
                logger.info("ImageGenerator: genai client not configured (%s). Image gen disabled.", e)

    def generate(
        self,
        brief: dict,
        ad_copy: dict,
        output_dir: Path,
        ad_id: str,
    ) -> Optional[Path]:
        """
        Generate one image for the ad; save to output_dir/creatives/{ad_id}.png.
        Returns path if successful, None otherwise. Never raises.
        """
        output_dir = Path(output_dir)
        creatives_dir = output_dir / "creatives"
        creatives_dir.mkdir(parents=True, exist_ok=True)
        out_path = creatives_dir / f"{ad_id}.png"

        if not _GENAI_AVAILABLE or self._client is None:
            logger.debug("Image generation skipped (google-genai not available or not configured).")
            return self._maybe_placeholder(creatives_dir, ad_id) if self.use_placeholder_on_failure else None

        try:
            prompt = _build_image_prompt(brief, ad_copy)
            response = self._client.models.generate_images(
                model=self.model,
                prompt=prompt,
                config=genai_types.GenerateImagesConfig(number_of_images=1),
            )
            if _save_image_from_genai(response, out_path):
                return out_path
        except Exception as e:
            logger.warning("Image generation failed for %s: %s", ad_id, e)

        return self._maybe_placeholder(creatives_dir, ad_id) if self.use_placeholder_on_failure else None

    def _maybe_placeholder(self, creatives_dir: Path, ad_id: str) -> Optional[Path]:
        """Write a minimal placeholder PNG so UI can show something. Never raises."""
        try:
            # Minimal 1x1 PNG (valid PNG bytes)
            png_1x1 = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            path = creatives_dir / f"{ad_id}_placeholder.png"
            path.write_bytes(png_1x1)
            return path
        except Exception as e:
            logger.warning("Could not write placeholder image: %s", e)
            return None

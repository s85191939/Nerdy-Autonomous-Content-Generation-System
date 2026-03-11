"""Image generation for ad creatives (v2). Never raises; returns None on any failure.

Strategy:
  1. Try Google Imagen API with a 12-second timeout.
  2. On ANY failure (timeout, API error, missing library), fall back to
     a fast programmatic image built with Pillow — a professional 1080×1080
     social-media creative with gradient background, brand colours, headline,
     CTA, and Varsity Tutors logo text.
"""

import hashlib
import logging
import math
import signal
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: google-genai for Imagen.  If not installed we skip straight to
# the Pillow fallback – which is the normal fast path.
# ---------------------------------------------------------------------------
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Pillow – required for the programmatic fallback
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Brand palette (Varsity Tutors)
# ---------------------------------------------------------------------------
_BRAND_COLORS = [
    # (gradient_start, gradient_end, accent, text_color)
    ((20, 90, 200), (10, 50, 140), (255, 195, 0), (255, 255, 255)),    # Blue → Dark Blue
    ((130, 50, 180), (70, 20, 120), (255, 200, 60), (255, 255, 255)),   # Purple → Dark Purple
    ((0, 150, 136), (0, 90, 80), (255, 220, 70), (255, 255, 255)),      # Teal → Dark Teal
    ((230, 80, 50), (160, 40, 20), (255, 230, 100), (255, 255, 255)),   # Red-Orange → Dark
    ((50, 50, 60), (25, 25, 30), (0, 200, 150), (255, 255, 255)),       # Dark charcoal
    ((0, 120, 200), (0, 60, 130), (255, 210, 0), (255, 255, 255)),      # Azure
    ((70, 45, 140), (35, 20, 80), (120, 220, 255), (255, 255, 255)),    # Indigo
    ((200, 50, 80), (120, 20, 50), (255, 200, 180), (255, 255, 255)),   # Crimson
    ((0, 100, 80), (0, 55, 45), (200, 255, 200), (255, 255, 255)),      # Forest
    ((30, 60, 110), (15, 30, 60), (100, 200, 255), (255, 255, 255)),    # Navy
]

# Decorative icons (simple Unicode-safe labels for each "topic")
_TOPIC_ICONS = {
    "sat": "📝",
    "math": "📐",
    "tutor": "🎓",
    "reading": "📚",
    "writing": "✍️",
    "science": "🔬",
    "college": "🏫",
    "test": "✅",
    "score": "📈",
    "study": "💡",
    "learn": "🧠",
    "grade": "⭐",
    "success": "🏆",
    "expert": "🎯",
    "online": "💻",
}


# ===================================================================
# Prompt builder
# ===================================================================

def _build_image_prompt(brief: dict, ad_copy: dict) -> str:
    """Build a short, brand-safe prompt for image generation."""
    product = brief.get("product", "product")
    audience = brief.get("audience", "audience")
    headline = ad_copy.get("headline") or ad_copy.get("primary_text", "")[:80]
    return (
        f"Professional advertising image for {product}, targeting {audience}. "
        f"Clean, modern, suitable for social media. No text overlay. "
        f"Concept: {headline}"
    ).strip()


# ===================================================================
# Imagen API helpers
# ===================================================================

def _save_image_from_genai(response: Any, path: Path) -> bool:
    """Save first generated image from google.genai response to path."""
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
            if isinstance(data, bytes):
                path.write_bytes(data)
                return True
        return False
    except Exception as e:
        logger.warning("Failed to save generated image: %s", e)
        return False


def _call_imagen_with_timeout(client, model: str, prompt: str, timeout_sec: int = 12) -> Any:
    """Call Imagen API in a thread with timeout. Returns response or None."""
    result_holder: List[Any] = [None]
    error_holder: List[Optional[Exception]] = [None]

    def _worker():
        try:
            result_holder[0] = client.models.generate_images(
                model=model,
                prompt=prompt,
                config=genai_types.GenerateImagesConfig(number_of_images=1),
            )
        except Exception as e:
            error_holder[0] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        logger.warning("Imagen API timed out after %ds — falling back to programmatic image.", timeout_sec)
        return None
    if error_holder[0] is not None:
        logger.warning("Imagen API error: %s — falling back.", error_holder[0])
        return None
    return result_holder[0]


# ===================================================================
# Programmatic (Pillow) fallback  — fast, deterministic, professional
# ===================================================================

def _pick_palette(ad_id: str) -> Tuple:
    """Deterministic palette pick based on ad_id hash."""
    idx = int(hashlib.md5(ad_id.encode()).hexdigest(), 16) % len(_BRAND_COLORS)
    return _BRAND_COLORS[idx]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a nice font; fall back gracefully."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> List[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines or [text]


def _draw_rounded_rect(draw: ImageDraw.Draw, xy: Tuple, radius: int, fill):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=fill)
    draw.pieslice([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=fill)


def generate_programmatic_image(
    brief: dict,
    ad_copy: dict,
    out_path: Path,
    ad_id: str = "ad",
) -> bool:
    """Create a professional 1080×1080 ad creative image using Pillow.

    Returns True on success, False on any failure. Never raises.
    """
    if not _PIL_AVAILABLE:
        return False

    try:
        W, H = 1080, 1080
        grad_start, grad_end, accent, text_color = _pick_palette(ad_id)

        # --- Gradient background ---
        img = Image.new("RGB", (W, H))
        for y in range(H):
            t = y / H
            r = int(grad_start[0] * (1 - t) + grad_end[0] * t)
            g = int(grad_start[1] * (1 - t) + grad_end[1] * t)
            b = int(grad_start[2] * (1 - t) + grad_end[2] * t)
            for x in range(W):
                img.putpixel((x, y), (r, g, b))
        draw = ImageDraw.Draw(img)

        # --- Decorative circles (background texture) ---
        for i in range(6):
            cx = (i * 237 + 150) % W
            cy = (i * 173 + 100) % H
            radius = 60 + (i * 31) % 80
            overlay_color = (*accent, 25)  # very faint
            # Use ellipse with semi-transparent feel via lighter color
            light = tuple(min(255, c + 40) for c in grad_start)
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         outline=(*light, ), width=2)

        # --- Top bar / brand badge ---
        bar_h = 100
        bar_color = tuple(max(0, c - 20) for c in grad_start)
        draw.rectangle([0, 0, W, bar_h], fill=bar_color)
        brand_font = _load_font(32)
        brand_label = brief.get("brand_name", "VARSITY TUTORS").upper()
        draw.text((40, 34), brand_label, fill=accent, font=brand_font)

        # Small "Ad" badge on right
        badge_font = _load_font(20)
        _draw_rounded_rect(draw, (W - 120, 30, W - 30, 70), 12, fill=accent)
        draw.text((W - 108, 38), "Sponsored", fill=(30, 30, 30), font=badge_font)

        # --- Topic icon (decorative) ---
        headline_text = ad_copy.get("headline", "") or ad_copy.get("primary_text", "")[:60]
        icon = "🎓"  # default
        lower_hl = headline_text.lower()
        for keyword, emoji in _TOPIC_ICONS.items():
            if keyword in lower_hl:
                icon = emoji
                break

        # Large decorative element in center-top area
        icon_font = _load_font(120)
        try:
            bbox = draw.textbbox((0, 0), icon, font=icon_font)
            iw = bbox[2] - bbox[0]
        except Exception:
            iw = 120
        draw.text(((W - iw) // 2, 130), icon, fill=text_color, font=icon_font)

        # --- Accent line ---
        line_y = 290
        line_margin = 120
        draw.rectangle([line_margin, line_y, W - line_margin, line_y + 4], fill=accent)

        # --- Headline ---
        headline_font = _load_font(52)
        lines = _wrap_text(headline_text.upper() if headline_text else "BOOST YOUR GRADES", headline_font, W - 160, draw)
        y_cursor = 320
        for line in lines[:4]:  # max 4 lines
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]
            draw.text(((W - lw) // 2, y_cursor), line, fill=text_color, font=headline_font)
            y_cursor += lh + 14

        # --- Description / subtext ---
        desc_text = ad_copy.get("description", "") or ad_copy.get("primary_text", "")[:120]
        if desc_text:
            desc_font = _load_font(28)
            desc_lines = _wrap_text(desc_text, desc_font, W - 200, draw)
            y_cursor += 20
            for dl in desc_lines[:3]:
                bbox = draw.textbbox((0, 0), dl, font=desc_font)
                dlw = bbox[2] - bbox[0]
                dlh = bbox[3] - bbox[1]
                light_text = tuple(min(255, c + 60) for c in text_color[:3])
                draw.text(((W - dlw) // 2, y_cursor), dl, fill=light_text, font=desc_font)
                y_cursor += dlh + 8

        # --- CTA Button ---
        cta_text = ad_copy.get("cta", "Learn More") or "Learn More"
        cta_font = _load_font(36)
        cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
        cta_w = cta_bbox[2] - cta_bbox[0]
        cta_h = cta_bbox[3] - cta_bbox[1]
        btn_w = cta_w + 80
        btn_h = cta_h + 40
        btn_x = (W - btn_w) // 2
        btn_y = max(y_cursor + 40, H - 260)
        _draw_rounded_rect(draw, (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), 20, fill=accent)
        draw.text((btn_x + 40, btn_y + 16), cta_text, fill=(30, 30, 30), font=cta_font)

        # --- Bottom bar with meta ---
        bottom_y = H - 100
        draw.rectangle([0, bottom_y, W, H], fill=bar_color)
        meta_font = _load_font(22)
        audience = brief.get("audience", "Students & Parents")
        platform = brief.get("platform", "Facebook / Instagram")
        draw.text((40, bottom_y + 20), f"📍 {platform}", fill=(*text_color[:3],), font=meta_font)
        draw.text((40, bottom_y + 52), f"🎯 {audience}", fill=(*text_color[:3],), font=meta_font)

        # Score badge if available
        score_font = _load_font(24)
        draw.text((W - 200, bottom_y + 20), "AI-Generated", fill=accent, font=score_font)
        draw.text((W - 200, bottom_y + 52), "Ad Creative", fill=accent, font=score_font)

        # --- Save ---
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_path), "PNG", optimize=True)
        logger.info("Generated programmatic ad image: %s", out_path)
        return True

    except Exception as e:
        logger.warning("Programmatic image generation failed for %s: %s", ad_id, e)
        return False


# ===================================================================
# Main ImageGenerator class
# ===================================================================

class ImageGenerator:
    """Generate creative images for ads. Never raises; returns None when generation fails."""

    def __init__(
        self,
        model: str = "imagen-3.0-generate-001",
        use_placeholder_on_failure: bool = True,
        imagen_timeout: int = 12,
    ):
        self.model = model
        self.use_placeholder_on_failure = use_placeholder_on_failure
        self.imagen_timeout = imagen_timeout
        self._client = None
        if _GENAI_AVAILABLE:
            try:
                self._client = genai.Client()
            except Exception as e:
                logger.info("ImageGenerator: genai client not configured (%s). Will use programmatic fallback.", e)

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

        Pipeline:
          1. Try Imagen API (with timeout)
          2. Fall back to programmatic Pillow image
        """
        output_dir = Path(output_dir)
        creatives_dir = output_dir / "creatives"
        creatives_dir.mkdir(parents=True, exist_ok=True)
        out_path = creatives_dir / f"{ad_id}.png"

        # --- Attempt 1: Imagen API (if available) ---
        if _GENAI_AVAILABLE and self._client is not None:
            try:
                prompt = _build_image_prompt(brief, ad_copy)
                response = _call_imagen_with_timeout(
                    self._client, self.model, prompt, timeout_sec=self.imagen_timeout
                )
                if response is not None and _save_image_from_genai(response, out_path):
                    logger.info("Imagen API generated image for %s", ad_id)
                    return out_path
            except Exception as e:
                logger.warning("Imagen attempt failed for %s: %s", ad_id, e)

        # --- Attempt 2: Fast programmatic fallback (Pillow) ---
        if generate_programmatic_image(brief, ad_copy, out_path, ad_id):
            return out_path

        # --- Attempt 3: Tiny placeholder (last resort) ---
        if self.use_placeholder_on_failure:
            return self._write_placeholder(creatives_dir, ad_id)

        return None

    def _write_placeholder(self, creatives_dir: Path, ad_id: str) -> Optional[Path]:
        """Write a minimal placeholder PNG. Never raises."""
        try:
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

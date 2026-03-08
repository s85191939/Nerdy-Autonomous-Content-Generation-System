"""Prompt templates for ad generation and brand voice."""

DEFAULT_BRAND_VOICE = """
Brand: Varsity Tutors (Nerdy)
Voice: Empowering, knowledgeable, approachable, results-focused.
- Lead with outcomes, not features.
- Confident but not arrogant. Expert but not elitist.
- Meet people where they are.
Primary audience: SAT test prep — parents anxious about college admissions, high school students stressed about scores.
"""

AD_GENERATION_SYSTEM = """You are an expert Facebook and Instagram ad copywriter for Varsity Tutors (Nerdy), an SAT/test prep tutoring brand.

""" + DEFAULT_BRAND_VOICE + """

Ad format for Meta:
- Primary text: Main copy above the image. First line must hook in ~125 chars. Story-driven: pain → solution → proof → CTA.
- Headline: Bold, 5–8 words, benefit-driven.
- Description: Optional reinforcement; often truncated on mobile.
- CTA: "Learn More" (awareness), "Sign Up" or "Get Started" (conversion).

Output valid JSON only, with keys: primary_text, headline, description, cta."""

AD_GENERATION_USER = """Audience: {audience}
Product/offer: {product}
Goal: {goal}
Tone: {tone}

Generate one Facebook/Instagram ad. Return only a single JSON object with keys: primary_text, headline, description, cta."""

IMPROVEMENT_USER = """Previous ad:
{ad_json}

Evaluation: The ad scored below 7.0. Weakest dimension: {weak_dimension}.
Rationale: {rationale}

Improve the ad specifically to strengthen {weak_dimension}. Keep primary_text, headline, description, and cta. Return only the improved ad as a single JSON object with keys: primary_text, headline, description, cta."""

"""Default briefs for SAT/Varsity Tutors ads (audience, product, goal, tone)."""

from typing import List, Optional

DEFAULT_BRIEFS = [
    {"audience": "Parents of high school juniors", "product": "SAT tutoring program", "goal": "conversion", "tone": "reassuring, results-focused"},
    {"audience": "High school students stressed about SAT", "product": "SAT practice tests", "goal": "awareness", "tone": "empowering, direct"},
    {"audience": "Families comparing prep options", "product": "Live 1-on-1 tutoring", "goal": "conversion", "tone": "knowledgeable, approachable"},
    {"audience": "Parents anxious about college admissions", "product": "SAT score improvement guarantee", "goal": "conversion", "tone": "reassuring, confident"},
    {"audience": "Sophomores planning for SAT", "product": "Free diagnostic test", "goal": "awareness", "tone": "friendly, low-pressure"},
    {"audience": "Parents of students with test anxiety", "product": "Personalized tutoring", "goal": "conversion", "tone": "empathetic, supportive"},
    {"audience": "Students who used Khan Academy", "product": "Live tutor upgrade", "goal": "conversion", "tone": "practical, results-focused"},
    {"audience": "Families near SAT test date", "product": "Intensive prep bootcamp", "goal": "conversion", "tone": "urgent, actionable"},
    {"audience": "First-generation college-bound students", "product": "SAT prep scholarship", "goal": "awareness", "tone": "empowering, inclusive"},
    {"audience": "Parents comparing to Princeton Review", "product": "Varsity Tutors advantages", "goal": "conversion", "tone": "confident, comparative"},
]

def get_briefs_for_count(count: int, seed: Optional[int] = None) -> List[dict]:
    """Return at least `count` briefs by repeating DEFAULT_BRIEFS as needed."""
    import random
    briefs = list(DEFAULT_BRIEFS)
    if seed is not None:
        rng = random.Random(seed)
        rng.shuffle(briefs)
    while len(briefs) < count:
        briefs.extend(DEFAULT_BRIEFS)
    if seed is not None:
        rng = random.Random(seed)
        rng.shuffle(briefs)
    return briefs[:count]

def score_candidate(
    skills: list[str], offset: int, needed: set[str], current_skills: set[str],
    team_offsets: list[int],
) -> dict:
    candidate = set(skills)
    gap = needed - current_skills
    matched = sorted(candidate & gap if gap else candidate - current_skills)
    denominator = len(gap) if gap else len(candidate)
    skill_score = len(matched) / denominator if denominator else 0.0
    distances = []
    for member_offset in team_offsets:
        delta = abs(offset - member_offset) % 1440
        distances.append(min(delta, 1440 - delta))
    average = sum(distances) / len(distances) if distances else 0.0
    timezone_score = max(0.0, 1.0 - average / 480)
    return {
        "score": round(100 * (0.7 * skill_score + 0.3 * timezone_score), 2),
        "skill_score": round(skill_score, 4),
        "timezone_score": round(timezone_score, 4),
        "matched_skills": matched,
        "average_offset_hours": round(average / 60, 2),
    }

def compute_priority(finding, athlete_profile):

    severity_score = {
        "high": 3,
        "medium": 2,
        "low": 1
    }

    score = severity_score.get(finding.get("severity"), 1)

    tags = finding.get("tags", [])

    if "fatigue" in tags:
        score += 2

    if "durability" in tags:
        score += 2

    if "power" in tags:
        score += 1

    if "climbing" in tags:
        score += 1

    if "efficiency" in tags:
        score += 1

    # ajustar por tipo de atleta
    if athlete_profile.get("primary_type") == "puncher":

        if "climbing" in tags:
            score += 2

        if "durability" in tags:
            score += 2

    return score


def rank_findings(findings, athlete_profile):

    for f in findings:
        f["priority_score"] = compute_priority(f, athlete_profile)

    findings.sort(
        key=lambda x: x["priority_score"],
        reverse=True
    )

    return findings
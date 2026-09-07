"""Deterministic screening rules; zero readings are never relabelled or imputed."""
def quality(history, target, step):
    values = history + target
    n = 1440 // step
    run = longest = 0
    for value in values:
        run = run + 1 if value == 0 else 0
        longest = max(longest, run)
    totals = [sum(values[i:i+n]) for i in range(0, len(values), n)]
    flags = []
    if sum(target) == 0:
        flags.append('zero_target_day')
    if sum(values) == 0:
        flags.append('zero_entire_eight_day_window')
    if longest * step >= 1440:
        flags.append('continuous_zero_at_least_24_hours')
    if any(0 < v <= .01 for v in totals):
        flags.append('near_zero_day_up_to_0_01_kwh_review_flag')
    return {'flags': flags, 'longest_zero_minutes': longest * step,
            'daily_totals_kwh': totals,
            'disposition': 'quarantine' if longest * step >= 1440 else 'retain',
            'cause': 'unresolved_zero_readings' if longest * step >= 1440 else None}

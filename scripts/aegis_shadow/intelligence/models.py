"""Optional walk-forward models fitted only by the owner-operated research command."""
from collections import defaultdict
from math import log1p
from statistics import mean

from scripts.aegis_shadow.intelligence.lab import group, number


def features(row):
    keys = ("momentum_short", "momentum_medium", "momentum_long", "relative_strength", "daily_volatility", "liquidity_proxy")
    values = [row.get(key) for key in keys]
    if not all(number(value) for value in values) or min(values[-2:]) <= 0:
        return None
    values[-1] = log1p(values[-1])
    return values


def fit_predict(rows, session, minimum, *, train_before=None):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    mature = defaultdict(list)
    pending = defaultdict(list)
    for row in rows:
        vector = features(row)
        if vector is None or not row["eligible"]:
            continue
        horizon = row["horizon"]
        outcome = row.get("outcome")
        if outcome and outcome["available_on"] < min(session, train_before or session):
            mature[horizon].append((row, vector, outcome["gross_return"] - outcome["round_trip_cost"]))
        if row["session"] == session and row.get("available_on", session) <= session:
            pending[horizon].append((row, vector))
    output = []
    for horizon, current in sorted(pending.items()):
        history = mature[horizon]
        if len(history) < minimum:
            continue
        x = [item[1] for item in history]
        y = [item[2] for item in history]
        test = [item[1] for item in current]
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(x, y).predict(test)
        boosting = GradientBoostingRegressor(random_state=0, max_depth=2).fit(x, y).predict(test)
        quantiles = [GradientBoostingRegressor(loss="quantile", alpha=q, random_state=0, max_depth=2)
                     .fit(x, y).predict(test) for q in (.1, .5, .9)]
        probabilities = [None] * len(current)
        days = sorted({item[0]["session"] for item in history})
        boundary = days[len(days) * 3 // 4]
        train = [item for item in history if item[0]["outcome"]["available_on"] < boundary]
        calibration = [item for item in history if item[0]["session"] >= boundary]
        if (len(train) >= minimum and len(calibration) >= minimum
                and len({item[2] > 0 for item in train}) == len({item[2] > 0 for item in calibration}) == 2):
            classifier = make_pipeline(StandardScaler(), LogisticRegression()).fit(
                [item[1] for item in train], [item[2] > 0 for item in train])
            scores = classifier.decision_function([item[1] for item in calibration]).reshape(-1, 1)
            calibrator = LogisticRegression().fit(scores, [item[2] > 0 for item in calibration])
            probabilities = calibrator.predict_proba(classifier.decision_function(test).reshape(-1, 1))[:, 1]
        # Pairwise cross-sectional ranking uses adjacent return-ranked pairs in each
        # historical session, avoiding a cross-date comparison and quadratic growth.
        cross_sections = defaultdict(list)
        for row, vector, target in history:
            cross_sections[row["session"]].append((target, row["security_id"], vector))
        pairs, labels = [], []
        for items in cross_sections.values():
            ordered = sorted(items)
            for low, high in zip(ordered, ordered[1:]):
                if low[0] == high[0]:
                    continue
                delta = [right - left for left, right in zip(low[2], high[2], strict=True)]
                pairs.extend((delta, [-value for value in delta]))
                labels.extend((1, 0))
        ranks = [None] * len(current)
        if len(pairs) >= minimum:
            ranking = LogisticRegression(random_state=0).fit(pairs, labels)
            ranks = ranking.decision_function(test)
        for i, (row, _) in enumerate(current):
            lower, median, upper = sorted(float(values[i]) for values in quantiles)
            output.append({"security_id": row["security_id"], "horizon": horizon, "group": group(row),
                           "ridge_net": float(ridge[i]), "boosted_net": float(boosting[i]),
                           "q10": lower, "q50": median, "q90": upper,
                           "calibrated_probability_positive_net": None if probabilities[i] is None else float(probabilities[i]),
                           "pairwise_rank_score": None if ranks[i] is None else float(ranks[i])})
    return output


def evaluate_models(rows, start, end, known_through, minimum, *, frozen=False):
    totals = defaultdict(list)
    for session in sorted({row["session"] for row in rows if start <= row["session"] <= end}):
        outcomes = {(row["security_id"], row["horizon"]): row["outcome"] for row in rows if row["session"] == session
                    and "outcome" in row and row["outcome"]["available_on"] <= known_through}
        for estimate in fit_predict(rows, session, minimum, train_before=start if frozen else None):
            key = estimate["security_id"], estimate["horizon"]
            if key in outcomes:
                truth = outcomes[key]["gross_return"] - outcomes[key]["round_trip_cost"]
                totals[estimate["horizon"]].append((truth, estimate))
    result = {}
    for horizon, items in sorted(totals.items()):
        calibrated = [(actual, est["calibrated_probability_positive_net"]) for actual, est in items
                      if est["calibrated_probability_positive_net"] is not None]
        result[str(horizon)] = {"scored": len(items), "ridge_mae": mean(abs(actual - est["ridge_net"]) for actual, est in items),
                                "boosting_mae": mean(abs(actual - est["boosted_net"]) for actual, est in items),
                                "central_80_coverage": mean(est["q10"] <= actual <= est["q90"] for actual, est in items),
                                "calibrated_samples": len(calibrated), "calibrated_brier": mean(
                                    (score - (actual > 0)) ** 2 for actual, score in calibrated) if calibrated else None}
    return result

"""
Genre rollup utility for UK event density project.

Purpose
-------
Sparse sub_genres get rolled up to their parent `genre` (and sparse genres up to
`segment`) based on a national count threshold. Before merging, each sparse
category is checked for geographic and seasonal concentration — if a "sparse"
sub_genre is actually clustered in one city/region or one month, merging it away
would erase a real signal rather than just remove noise, so it gets flagged
instead of silently merged.

"Undefined" values are never merged into a real category — they're missing
data, not a rare-but-real genre — and are kept as an explicit label.
"""

import pandas as pd
import numpy as np


UNDEFINED_LABELS = {"undefined", "unknown", "n/a", "", "nan"}


def _is_undefined(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(UNDEFINED_LABELS) | series.isna()


def flag_concentrated_categories(
    df: pd.DataFrame,
    category_col: str,
    location_col: str,
    date_col: str,
    count_threshold: int,
    concentration_threshold: float = 0.7,
    min_n_for_concentration_check: int = 5,
) -> pd.DataFrame:
    """
    For each category below count_threshold, check whether it's concentrated
    in a single location or a single month rather than genuinely rare.

    Categories with fewer than min_n_for_concentration_check events are NOT
    eligible to be flagged as concentrated — with n=1 or n=2, a 100% location
    share is mechanical (one event is trivially "all" in one place) and tells
    you nothing about whether the genre is genuinely regional. Below this
    sample size the concentration check is meaningless, so these categories
    fall through to the normal merge rule instead of being protected.

    Returns a DataFrame with one row per sparse category, flagging:
      - top_location_share: fraction of its events in its single most common location
      - top_month_share: fraction of its events in its single most common month
      - concentrated: True if either share exceeds concentration_threshold
                      AND n_events >= min_n_for_concentration_check

    Categories flagged as concentrated are candidates to KEEP SEPARATE (or
    merge only within their region/season) rather than roll up nationally,
    since collapsing them would flatten a real geographic/seasonal pattern.
    """
    work = df[~_is_undefined(df[category_col])].copy()
    work["_month"] = pd.to_datetime(work[date_col]).dt.month

    counts = work[category_col].value_counts()
    sparse_cats = counts[counts < count_threshold].index

    rows = []
    for cat in sparse_cats:
        sub = work[work[category_col] == cat]
        n = len(sub)
        top_loc_share = sub[location_col].value_counts(normalize=True).iloc[0] if n else np.nan
        top_month_share = sub["_month"].value_counts(normalize=True).iloc[0] if n else np.nan
        eligible = n >= min_n_for_concentration_check
        rows.append({
            category_col: cat,
            "n_events": n,
            "top_location_share": round(top_loc_share, 2),
            "top_month_share": round(top_month_share, 2),
            "eligible_for_concentration_flag": eligible,
            "concentrated": eligible and (
                (top_loc_share >= concentration_threshold)
                or (top_month_share >= concentration_threshold)
            ),
        })

    return pd.DataFrame(rows).sort_values("n_events")


def rollup_genres(
    df: pd.DataFrame,
    subgenre_col: str = "sub_genre",
    genre_col: str = "genre",
    segment_col: str = "segment",
    location_col: str = "city",
    date_col: str = "date",
    subgenre_threshold: int = 10,
    genre_threshold: int = 10,
    concentration_threshold: float = 0.7,
    min_n_for_concentration_check: int = 5,
    protect_concentrated: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Roll sparse sub_genres up to genre, and sparse genres up to segment,
    based on national count thresholds.

    "Undefined" (and equivalent missing-style labels) are left untouched —
    never merged into a real category.

    If protect_concentrated=True, a sparse category that is geographically or
    seasonally concentrated (see flag_concentrated_categories) is NOT merged
    even if it's below the threshold; it's left as-is and flagged in the log,
    since merging it would erase a real regional/seasonal effect rather than
    just denoise.

    Returns
    -------
    (result_df, merge_log)
      result_df : copy of df with two new columns:
                    - 'sub_genre_grouped'
                    - 'genre_grouped'
      merge_log : DataFrame recording every merge decision made, for
                  reproducibility / write-up documentation.
    """
    out = df.copy()
    log_rows = []

    # --- Sub-genre -> genre rollup ---
    flagged = flag_concentrated_categories(
        out, subgenre_col, location_col, date_col, subgenre_threshold,
        concentration_threshold, min_n_for_concentration_check
    )
    protected = set(flagged.loc[flagged["concentrated"], subgenre_col]) if protect_concentrated else set()

    sub_counts = out.loc[~_is_undefined(out[subgenre_col]), subgenre_col].value_counts()
    sparse_subgenres = set(sub_counts[sub_counts < subgenre_threshold].index) - protected

    def map_subgenre(row):
        sg = row[subgenre_col]
        if _is_undefined(pd.Series([sg])).iloc[0]:
            return sg  # leave undefined as-is
        if sg in sparse_subgenres:
            return row[genre_col]  # roll up to parent genre
        return sg

    out["sub_genre_grouped"] = out.apply(map_subgenre, axis=1)

    for sg in sparse_subgenres:
        parent = out.loc[out[subgenre_col] == sg, genre_col].mode().iloc[0]
        # Skip logging (and treat as a no-op) when sub_genre and its parent
        # genre already share the same label — this isn't a real collapse,
        # just two hierarchy levels happening to be named identically.
        action = "merged_to_parent" if sg != parent else "no_op_same_label"
        log_rows.append({
            "level": "sub_genre", "category": sg, "action": action,
            "merged_into": parent, "n_events": int(sub_counts.get(sg, 0)),
        })
    for sg in protected:
        row = flagged.loc[flagged[subgenre_col] == sg].iloc[0]
        log_rows.append({
            "level": "sub_genre", "category": sg, "action": "kept_separate_concentrated",
            "merged_into": None, "n_events": int(row["n_events"]),
        })

    # --- Genre -> segment rollup (using already-grouped sub_genre as the genre col won't change segment logic) ---
    flagged_g = flag_concentrated_categories(
        out, genre_col, location_col, date_col, genre_threshold,
        concentration_threshold, min_n_for_concentration_check
    )
    protected_g = set(flagged_g.loc[flagged_g["concentrated"], genre_col]) if protect_concentrated else set()

    genre_counts = out.loc[~_is_undefined(out[genre_col]), genre_col].value_counts()
    sparse_genres = set(genre_counts[genre_counts < genre_threshold].index) - protected_g

    def map_genre(row):
        g = row[genre_col]
        if _is_undefined(pd.Series([g])).iloc[0]:
            return g
        if g in sparse_genres:
            return row[segment_col]
        return g

    out["genre_grouped"] = out.apply(map_genre, axis=1)

    for g in sparse_genres:
        parent = out.loc[out[genre_col] == g, segment_col].mode().iloc[0]
        action = "merged_to_parent" if g != parent else "no_op_same_label"
        log_rows.append({
            "level": "genre", "category": g, "action": action,
            "merged_into": parent, "n_events": int(genre_counts.get(g, 0)),
        })
    for g in protected_g:
        row = flagged_g.loc[flagged_g[genre_col] == g].iloc[0]
        log_rows.append({
            "level": "genre", "category": g, "action": "kept_separate_concentrated",
            "merged_into": None, "n_events": int(row["n_events"]),
        })

    merge_log = pd.DataFrame(log_rows).sort_values(["level", "n_events"])
    return out, merge_log


if __name__ == "__main__":
    df = pd.read_csv("/data/events.csv")

    result, log = rollup_genres(
        df,
        subgenre_threshold=10,
        genre_threshold=10,
        concentration_threshold=0.7,
        min_n_for_concentration_check=5,
    )

    print("=== Merge log ===")
    print(log.to_string(index=False))

    print("\n=== sub_genre_grouped value counts (top 20) ===")
    print(result["sub_genre_grouped"].value_counts().head(20))

    print("\n=== genre_grouped value counts ===")
    print(result["genre_grouped"].value_counts())

    result.to_csv("data/events_new_genres.csv", index=False)
    log.to_csv("data/merge_log.csv", index=False)

"""
Sunburst plot of event counts (segment -> genre -> sub_genre) for a given
city/area and date range.

Uses the cleaned 'genre_grouped' / 'sub_genre_grouped' columns produced by
genre_rollup.py, so the chart reflects the de-sparsified hierarchy rather
than the raw long tail of one-off sub_genres.
"""

import pandas as pd
import plotly.express as px


def plot_genre_sunburst(
    df: pd.DataFrame,
    city: str | list[str] | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    segment_col: str = "segment",
    genre_col: str = "genre_grouped",
    subgenre_col: str = "sub_genre_grouped",
    date_col: str = "date",
    city_col: str = "city",
    exclude_undefined: bool = True,
    title: str | None = None,
):
    """
    Build a sunburst chart (segment -> genre -> sub_genre) showing the number
    of events in a given city/area and date range.

    Parameters
    ----------
    df : the events dataframe (post genre_rollup, containing genre_grouped /
         sub_genre_grouped columns).
    city : a single city name, a list of city names, or None for all cities.
           Matching is exact on the `city_col` values as they appear in the
           data (e.g. "London", "Newcastle Upon Tyne") - check df[city_col]
           .unique() if a filter returns nothing.
    start_date, end_date : inclusive date bounds (any pandas-parseable
           format, e.g. "2026-09-01"). Either can be omitted to leave that
           side of the range open.
    exclude_undefined : drop rows where genre/sub_genre is "Undefined" before
           plotting. These are missing-data placeholders (see genre_rollup.py)
           rather than a real category, and including them would show a
           misleadingly large "Undefined" wedge.
    title : custom chart title. If None, one is generated from the filters.

    Returns
    -------
    (fig, filtered_df)
        fig : plotly.graph_objects.Figure - call fig.show() to display.
        filtered_df : the filtered dataframe actually used, useful for
                      sanity-checking event counts or debugging an
                      unexpectedly empty chart.
    """
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col])

    filters_applied = []

    if city is not None:
        cities = [city] if isinstance(city, str) else list(city)
        work = work[work[city_col].isin(cities)]
        filters_applied.append(", ".join(cities))

    if start_date is not None:
        work = work[work[date_col] >= pd.to_datetime(start_date)]
    if end_date is not None:
        work = work[work[date_col] <= pd.to_datetime(end_date)]
    if start_date is not None or end_date is not None:
        s = pd.to_datetime(start_date).date() if start_date else "start"
        e = pd.to_datetime(end_date).date() if end_date else "end"
        filters_applied.append(f"{s} to {e}")

    if exclude_undefined:
        for col in (segment_col, genre_col, subgenre_col):
            work = work[work[col].astype(str).str.lower() != "undefined"]
            work = work[work[col].notna()]

    if work.empty:
        all_dates = pd.to_datetime(df[date_col])
        raise ValueError(
            "No events match the given filters. Check the city name spelling "
            f"(e.g. df['{city_col}'].unique()) and that the date range overlaps "
            f"the data (data spans {all_dates.min().date()} to "
            f"{all_dates.max().date()})."
        )

    counts = (
        work.groupby([segment_col, genre_col, subgenre_col])
        .size()
        .reset_index(name="event_count")
    )

    if title is None:
        title = "Event breakdown by genre"
        if filters_applied:
            title += " — " + " | ".join(filters_applied)
    total = counts["event_count"].sum()
    title += f"  ({total:,} events)"

    fig = px.sunburst(
        counts,
        path=[segment_col, genre_col, subgenre_col],
        values="event_count",
        title=title,
    )
    fig.update_traces(
        textinfo="label+value",
        hovertemplate="<b>%{label}</b><br>Events: %{value}<extra></extra>",
    )
    fig.update_layout(margin=dict(t=60, l=10, r=10, b=10))

    return fig, work


if __name__ == "__main__":
    df = pd.read_csv("/home/claude/genre_merge/events_with_grouped_genres.csv")

    # Example: London, next 3 months from the dataset's earliest date
    fig, filtered = plot_genre_sunburst(
        df,
        city="London",
        start_date="2026-07-01",
        end_date="2026-09-30",
    )
    fig.write_html("/home/claude/genre_merge/sunburst_london_summer.html")
    print(f"Filtered rows: {len(filtered)}")
    print("Saved to sunburst_london_summer.html")

    # Example: all cities, whole dataset
    fig2, filtered2 = plot_genre_sunburst(df)
    fig2.write_html("/home/claude/genre_merge/sunburst_all_uk.html")
    print(f"All-UK filtered rows: {len(filtered2)}")

"""
Sunburst plot of event counts (segment -> genre -> sub_genre) for a given
area and date range.

Small slices are automatically collapsed into an 'Other' bucket via
_group_small_slices(), so the raw genre / sub_genre columns from events.csv
can be passed in directly — no prior genre rollup step is needed.
"""

import pandas as pd
import plotly.express as px


def plot_genre_sunburst(
    df: pd.DataFrame,
    area: str | list[str] | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    segment_col: str = "segment",
    genre_col: str = "genre",
    subgenre_col: str = "sub_genre",
    date_col: str = "date",
    area_col: str = "area",
    exclude_undefined: bool = True,
    title: str | None = None,
    min_slice_share: float = 0.02,
):
    """
    Build a sunburst chart (segment -> genre -> sub_genre) showing the number
    of events in a given area and date range.

    Parameters
    ----------
    df : the events dataframe. The raw genre / sub_genre columns from
         events.csv can be passed directly — small slices are collapsed
         into "Other" automatically by min_slice_share.
    area : a single area name, a list of area names, or None for all areas.
           For non-London cities this is the city name (e.g. "Manchester").
           For London this is the borough name (e.g. "Camden", "Hackney").
           Matching is exact on the `area_col` values as they appear in the
           data — check df[area_col].unique() if a filter returns nothing.
    start_date, end_date : inclusive date bounds (any pandas-parseable
           format, e.g. "2026-09-01"). Either can be omitted to leave that
           side of the range open.
    exclude_undefined : drop rows where segment/genre/sub_genre is
           "Undefined" or null before plotting. These are missing-data
           placeholders in the Ticketmaster data rather than real
           categories.
    title : custom chart title. If None, one is generated from the filters.
    min_slice_share : categories whose angular width would be smaller than
           this fraction of the full circle are grouped into an "Other"
           slice. Since slice width equals count / grand_total, this
           threshold is applied against the grand total — which is what
           actually determines whether a wedge is visually a sliver.
           Applied at two levels:
             - genre: any genre whose total (summed across its sub_genres)
               is below this share of the grand total becomes "Other"
               within its segment; its sub_genres collapse into that
               "Other" too.
             - sub_genre: any sub_genre whose count is below this share of
               the grand total becomes "Other" within its genre.
           Default 0.02 groups anything occupying less than 2% of the
           circle. Set to 0 to disable grouping and show every category.

    Returns
    -------
    (fig, filtered_df, total_events)
        fig : plotly.graph_objects.Figure - call fig.show() to display.
        filtered_df : the filtered dataframe actually used, useful for
                      sanity-checking event counts or debugging an
                      unexpectedly empty chart.
        total_events : int, total number of events represented in the chart.
    """
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col])

    filters_applied = []

    if area is not None:
        areas = [area] if isinstance(area, str) else list(area)
        work = work[work[area_col].isin(areas)]
        filters_applied.append(", ".join(areas))

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
            "No events match the given filters. Check the area name spelling "
            f"(e.g. df['{area_col}'].unique()) and that the date range overlaps "
            f"the data (data spans {all_dates.min().date()} to "
            f"{all_dates.max().date()})."
        )

    counts = (
        work.groupby([segment_col, genre_col, subgenre_col])
        .size()
        .reset_index(name="event_count")
    )

    if title is None:
        title = ""
        if filters_applied:
            title +=  " | ".join(filters_applied)
    total = counts["event_count"].sum()
    title += f"  ({total:,} events)"

    counts = _group_small_slices(
        counts, segment_col, genre_col, subgenre_col, min_slice_share
    )

    fig = px.sunburst(
        counts,
        path=[segment_col, genre_col, subgenre_col],
        values="event_count",
        title=title,
    )
    fig.update_traces(
        textinfo="label+value",
        hovertemplate="<b>%{label}</b><br>Events: %{value}<extra></extra>",
        marker=dict(line=dict(width=0)),
    )
    fig.update_layout(margin=dict(t=60, l=10, r=10, b=10))

    return fig, work, int(total)


def _group_small_slices(
    counts: pd.DataFrame,
    segment_col: str,
    genre_col: str,
    subgenre_col: str,
    min_slice_share: float,
) -> pd.DataFrame:
    """
    Collapse small categories into an 'Other' bucket, using the grand total
    as the denominator — which is correct because a slice's angular width in
    a sunburst is proportional to its count divided by the grand total, not
    its share of its parent.

    Genre level
    -----------
    Any genre whose total (summed across all its sub_genres) is below
    min_slice_share of the grand total is relabelled "Other" within its
    segment. Its sub_genres are collapsed to "Other" too so they don't
    appear as labelled slivers underneath a wedge called "Other".

    Sub-genre level
    ---------------
    Any sub_genre whose count is below min_slice_share of the grand total
    is relabelled "Other" within its (segment, genre).

    Both steps are followed by a re-aggregation so multiple rows that now
    share the same (segment, genre, sub_genre) label are summed.
    """
    if min_slice_share <= 0:
        return counts

    grand_total = counts["event_count"].sum()
    threshold = min_slice_share * grand_total
    counts = counts.copy()

    # --- Genre level -----------------------------------------------------
    genre_totals = (
        counts.groupby([segment_col, genre_col])["event_count"]
        .transform("sum")
    )
    small_genre = genre_totals < threshold
    counts.loc[small_genre, genre_col]    = "Other"
    counts.loc[small_genre, subgenre_col] = "Other"

    # Re-aggregate before sub_genre pass.
    counts = (
        counts.groupby([segment_col, genre_col, subgenre_col])["event_count"]
        .sum()
        .reset_index()
    )

    # --- Sub-genre level -------------------------------------------------
    small_subgenre = counts["event_count"] < threshold
    counts.loc[small_subgenre, subgenre_col] = "Other"

    # Final re-aggregation.
    counts = (
        counts.groupby([segment_col, genre_col, subgenre_col])["event_count"]
        .sum()
        .reset_index()
    )
    return counts


if __name__ == "__main__":
    df = pd.read_csv("data/events.csv")

    # Example: Westminster borough, summer 2026
    fig, filtered, total_events = plot_genre_sunburst(
        df,
        area="Westminster",
        start_date="2026-07-01",
        end_date="2026-09-30",
    )
    fig.write_html("sunburst_westminster_summer.html")
    print(f"Filtered rows: {len(filtered)} | Total events: {total_events}")
    print("Saved to sunburst_westminster_summer.html")

    # Example: all areas, whole dataset
    fig2, filtered2, total_events2 = plot_genre_sunburst(df)
    fig2.write_html("sunburst_all_uk.html")
    print(f"All-UK filtered rows: {len(filtered2)} | Total events: {total_events2}")
"""Dashboard Streamlit do przeglądania wyników HRR60 zapisanych w SQLite.

Nie zawiera schedulera ani powiadomień (Discord) - to czysto wizualny
podgląd danych zebranych przez `scripts/sync_last_activity.py` (albo
przez `POST /sync`), plus opcjonalny przycisk do ręcznego dociągnięcia
nowych aktywności z Garmina bez wychodzenia z przeglądarki.

Uruchomienie (z katalogu głównego repo, po aktywacji .venv):

    .\\.venv\\Scripts\\streamlit.exe run scripts\\dashboard.py

Otworzy się w przeglądarce pod http://localhost:8501 (Streamlit robi to
automatycznie). Odśwież stronę (klawisz R w Streamlit albo przycisk w UI),
żeby zobaczyć nowo zsynchronizowane dane.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from garmin_hrr.config import get_settings  # noqa: E402
from garmin_hrr.storage import Storage  # noqa: E402
from garmin_hrr.sync import sync_activities_by_date  # noqa: E402

st.set_page_config(page_title="Garmin HRR60 Tracker", page_icon="❤️", layout="wide")


@st.cache_resource
def _get_storage() -> Storage:
    return Storage(get_settings().database_path)


def _load_activities() -> pd.DataFrame:
    rows = _get_storage().list_activities()
    if not rows:
        return pd.DataFrame(
            columns=[
                "activity_id",
                "activity_name",
                "start_time",
                "hr_at_t0",
                "hr_at_t1",
                "hrr60",
            ]
        )
    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    return df.sort_values("start_time")


st.title("❤️ Garmin HRR60 Tracker")
st.caption(
    "HRR60 = tętno na końcu głównej sesji treningu minus tętno 60 sekund później. "
    "Większy spadek zwykle oznacza lepszą regenerację/formę sercowo-naczyniową."
)

with st.expander("🔄 Pobierz nowe aktywności z Garmina", expanded=False):
    col1, col2, col3 = st.columns([1, 1, 1])
    default_start = pd.Timestamp.today().replace(day=1).date()
    start_date = col1.date_input("Od daty", value=default_start)
    end_date = col2.date_input("Do daty", value=pd.Timestamp.today().date())
    if col3.button("Synchronizuj", type="primary"):
        with st.spinner("Logowanie do Garmin Connect i pobieranie aktywności..."):
            try:
                outcomes = sync_activities_by_date(
                    start_date.isoformat(), end_date.isoformat()
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Synchronizacja nie powiodła się: {exc}")
            else:
                ok = sum(1 for o in outcomes if o.status == "ok")
                skipped = sum(1 for o in outcomes if o.status.startswith("skipped"))
                errors = sum(1 for o in outcomes if o.status == "error")
                st.success(
                    f"Sprawdzono {len(outcomes)} aktywności: {ok} policzonych, "
                    f"{skipped} pominiętych, {errors} błędów."
                )
                st.rerun()

df = _load_activities()

if df.empty:
    st.info(
        "Brak zapisanych wyników. Uruchom `scripts\\sync_last_activity.py` albo "
        "skorzystaj z sekcji 'Pobierz nowe aktywności z Garmina' powyżej."
    )
    st.stop()

st.sidebar.header("Wykres HRR60")
min_date = df["start_time"].min().date()
max_date = df["start_time"].max().date()
default_chart_start = max(min_date, max_date - timedelta(days=30))
chart_date_range = st.sidebar.date_input(
    "Zakres dat wykresu",
    value=(default_chart_start, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(chart_date_range, tuple) and len(chart_date_range) == 2:
    chart_start, chart_end = chart_date_range
    chart_mask = (df["start_time"].dt.date >= chart_start) & (
        df["start_time"].dt.date <= chart_end
    )
    chart_df = df[chart_mask]
else:
    chart_df = df

if chart_df.empty:
    st.warning("Brak aktywności w wybranym zakresie dat wykresu.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Liczba treningów", len(chart_df))
col2.metric("Średnie HRR60", f"{chart_df['hrr60'].mean():.1f} bpm")
col3.metric("Najlepsze HRR60", f"{chart_df['hrr60'].max():.1f} bpm")
non_zero_hrr = chart_df.loc[chart_df["hrr60"].ne(0), "hrr60"]
weakest_hrr = f"{non_zero_hrr.min():.1f} bpm" if not non_zero_hrr.empty else "brak"
col4.metric("Najsłabsze HRR60", weakest_hrr)

st.subheader("HRR60 w czasie")
chart_data = chart_df.set_index("start_time")[["hrr60"]].rename(
    columns={"hrr60": "HRR60 (bpm)"}
)
st.line_chart(chart_data)

st.subheader("Szczegóły")
display_df = df[
    ["start_time", "activity_name", "hr_at_t0", "hr_at_t1", "hrr60", "activity_id"]
].rename(
    columns={
        "start_time": "Start",
        "activity_name": "Aktywność",
        "hr_at_t0": "HR @ t0",
        "hr_at_t1": "HR @ t0+60s",
        "hrr60": "HRR60 (bpm)",
        "activity_id": "ID aktywności",
    }
)
display_df["HR @ t0"] = display_df["HR @ t0"].round().astype("Int64")
display_df["HR @ t0+60s"] = display_df["HR @ t0+60s"].round().astype("Int64")
display_df["HRR60 (bpm)"] = display_df["HRR60 (bpm)"].round(1)
st.dataframe(
    display_df.sort_values("Start", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "HRR60 (bpm)": st.column_config.NumberColumn(format="%.1f"),
    },
)

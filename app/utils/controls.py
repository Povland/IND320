import streamlit as st

from utils.data import available_area_numbers, available_dates, load_reservoir_data

# The three types of areas in NVE's data, with the labels shown in the app
AREA_TYPES = {
    "EL": "Price areas (EL 1–5)",
    "NO": "All of Norway (NO)",
    "VASS": "Watercourse areas (VASS)",
}

# Key prefix for the global selection in the sidebar
GLOBAL_KEY = "global"


# Gives a widget its starting value before it is drawn, if it doesn't have one yet
def _restore(widget_key, value):
    if widget_key not in st.session_state:
        st.session_state[widget_key] = value


# Radio buttons for choosing EL, NO or VASS.
# memory_key decides where the choice is remembered: "area_type_memory" is the global choice (the sidebar),
# a page's own key makes it a local choice that starts from the global one but doesn't change it.
# allowed limits the options (the weather page has no NO, since there is no weather polygon for all of Norway).
# The memory is only updated when the user changes the choice (on_change), not when a page shows a default
def area_type_selector(key, allowed=None, memory_key="area_type_memory", horizontal=True):
    options = [area_type for area_type in AREA_TYPES if allowed is None or area_type in allowed]
    widget_key = f"{key}_area_type"

    remembered = st.session_state.get(memory_key, st.session_state.get("area_type_memory", "EL"))
    if remembered not in options:
        remembered = options[0]
    _restore(widget_key, remembered)
    if st.session_state[widget_key] not in options:
        st.session_state[widget_key] = remembered

    def remember():
        st.session_state[memory_key] = st.session_state[widget_key]

    return st.radio(
        "Type of area",
        options=options,
        format_func=AREA_TYPES.get,
        horizontal=horizontal,
        key=widget_key,
        on_change=remember,
    )


# Dropdown with a checkbox per area, for choosing which areas of the chosen type to show: all, some, one or none
def area_number_selector(key, area_type, area_numbers):
    memory = st.session_state.setdefault("area_numbers_memory", {})
    remembered = memory.get(area_type, area_numbers)

    # One checkbox per area, with its own key per area type (e.g. "global_area_EL_3")
    keys = {nr: f"{key}_area_{area_type}_{nr}" for nr in area_numbers}
    for nr, widget_key in keys.items():
        _restore(widget_key, nr in remembered)

    # Text on the dropdown button, based on which boxes are ticked
    ticked = [nr for nr, widget_key in keys.items() if st.session_state[widget_key]]
    if len(ticked) == len(area_numbers):
        summary = "All"
    elif not ticked:
        summary = "None"
    else:
        summary = ", ".join(f"{area_type} {nr}" for nr in ticked)

    # Ticks or unticks every box. Runs as a callback, i.e. before the checkboxes are drawn
    def set_all(value):
        for widget_key in keys.values():
            st.session_state[widget_key] = value

    with st.popover(f"Areas: {summary}"):
        all_column, none_column = st.columns(2)
        all_column.button("Select all", on_click=set_all, args=(True,), key=f"{key}_{area_type}_all")
        none_column.button("Select none", on_click=set_all, args=(False,), key=f"{key}_{area_type}_none")

        for nr, widget_key in keys.items():
            st.checkbox(f"{area_type} {nr}", key=widget_key)

    chosen = [nr for nr, widget_key in keys.items() if st.session_state[widget_key]]
    memory[area_type] = chosen
    return chosen


# Slider for choosing which weeks of data to use
def period_selector(key, dates):
    widget_key = f"{key}_period"
    full_period = (dates[0], dates[-1])

    # If the remembered period no longer matches the data (e.g. a new week was published), reset it
    remembered = st.session_state.get("period_memory", full_period)
    if remembered[0] not in dates or remembered[1] not in dates:
        remembered = full_period
    _restore(widget_key, remembered)

    start, end = st.select_slider(
        "Period",
        options=dates,
        value=full_period,   # tells Streamlit this is a range slider (two handles)
        format_func=lambda date: date.strftime("%Y-%m-%d"),
        key=widget_key,
    )
    st.session_state["period_memory"] = (start, end)
    return start, end


# ---------------------------------------------------------------------------------------------
# The global selection: drawn once in the sidebar by streamlit_app.py, on the pages that use it.
# Being in the entry file makes it the same widget on every page. On pages where it isn't shown,
# Streamlit forgets the widgets, and the memory above puts the choice back when it is shown again.
# ---------------------------------------------------------------------------------------------


# Draws the global selection in the sidebar and stores it in st.session_state["global_selection"].
# None if the reservoir data isn't available
def global_selection():
    if load_reservoir_data().empty:
        st.session_state["global_selection"] = None
        return None

    with st.sidebar:
        st.subheader("Data selection")
        st.caption("Shared by all pages that show it")
        area_type = area_type_selector(GLOBAL_KEY, horizontal=False)
        area_numbers = area_number_selector(GLOBAL_KEY, area_type, available_area_numbers(area_type))
        start, end = period_selector(GLOBAL_KEY, available_dates())

    selection = {"area_type": area_type, "area_numbers": area_numbers, "start": start, "end": end}
    st.session_state["global_selection"] = selection
    return selection


# The global selection, for the pages. Stops the page with a message if the reservoir data isn't available
def get_global_selection():
    selection = st.session_state.get("global_selection")
    if selection is None:
        st.warning("Reservoir data is not available. Please check the data source.")
        st.stop()
    return selection


# ---------------------------------------------------------------------------------------------
# Local selectors, drawn on the analysis pages themselves
# ---------------------------------------------------------------------------------------------


# Dropdown for choosing ONE area, for the analysis pages (STL, spectrogram, SPC, LOF all work on one series).
# Local: the choice is remembered per page and doesn't change the global choice of areas.
# The first time, it starts on the first area chosen in the sidebar, so the pages feel connected
def single_area_selector(key, area_type, area_numbers):
    widget_key = f"{key}_single_area_{area_type}"
    memory = st.session_state.setdefault("single_area_memory", {})

    remembered = memory.get(widget_key)
    if remembered not in area_numbers:
        chosen_globally = st.session_state.get("area_numbers_memory", {}).get(area_type, [])
        chosen_globally = [nr for nr in chosen_globally if nr in area_numbers]
        remembered = chosen_globally[0] if chosen_globally else area_numbers[0]
    _restore(widget_key, remembered)

    # If the options changed since the widget was last drawn, start again from the remembered area
    if st.session_state[widget_key] not in area_numbers:
        st.session_state[widget_key] = remembered

    def remember():
        memory[widget_key] = st.session_state[widget_key]

    return st.selectbox(
        "Area",
        options=area_numbers,
        format_func=lambda nr: f"{area_type} {nr}",
        key=widget_key,
        on_change=remember,
    )


# Dropdown for choosing one year, newest first. Local: remembered per page
def year_selector(key, years):
    widget_key = f"{key}_year"
    memory_key = f"{key}_year_memory"
    remembered = st.session_state.get(memory_key)
    if remembered not in years:
        remembered = years[0]
    _restore(widget_key, remembered)

    if st.session_state[widget_key] not in years:
        st.session_state[widget_key] = remembered

    def remember():
        st.session_state[memory_key] = st.session_state[widget_key]

    return st.selectbox("Year", options=years, key=widget_key, on_change=remember)
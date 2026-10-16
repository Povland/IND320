import streamlit as st

# The three types of areas in NVE's data, with the labels shown in the app
AREA_TYPES = {
    "EL": "Price areas (EL 1–5)",
    "NO": "All of Norway (NO)",
    "VASS": "Watercourse areas (VASS)",
}


# Gives a widget its starting value before it is drawn, if it doesn't have one yet
def _restore(widget_key, value):
    if widget_key not in st.session_state:
        st.session_state[widget_key] = value


# Radio buttons for choosing EL, NO or VASS
def area_type_selector(page):
    widget_key = f"{page}_area_type"
    _restore(widget_key, st.session_state.get("area_type_memory", "EL"))

    choice = st.radio(
        "Type of area",
        options=list(AREA_TYPES),
        format_func=AREA_TYPES.get,
        horizontal=True,
        key=widget_key,
    )
    st.session_state["area_type_memory"] = choice
    return choice


# Dropdown with a checkbox per area, for choosing which areas of the chosen type to show: all, some, one or none. 
def area_number_selector(page, area_type, area_numbers):
    memory = st.session_state.setdefault("area_numbers_memory", {})
    remembered = memory.get(area_type, area_numbers)

    # One checkbox per area, with its own key per page and area type (e.g. "data_area_EL_3")
    keys = {nr: f"{page}_area_{area_type}_{nr}" for nr in area_numbers}
    for nr, key in keys.items():
        _restore(key, nr in remembered)

    # Text on the dropdown button, based on which boxes are ticked
    ticked = [nr for nr, key in keys.items() if st.session_state[key]]
    if len(ticked) == len(area_numbers):
        summary = "All"
    elif not ticked:
        summary = "None"
    else:
        summary = ", ".join(f"{area_type} {nr}" for nr in ticked)

    # Ticks or unticks every box. Runs as a callback, i.e. before the checkboxes are drawn
    def set_all(value):
        for key in keys.values():
            st.session_state[key] = value

    with st.popover(f"Areas: {summary}"):
        all_column, none_column = st.columns(2)
        all_column.button("Select all", on_click=set_all, args=(True,), key=f"{page}_{area_type}_all")
        none_column.button("Select none", on_click=set_all, args=(False,), key=f"{page}_{area_type}_none")

        for nr, key in keys.items():
            st.checkbox(f"{area_type} {nr}", key=key)

    chosen = [nr for nr, key in keys.items() if st.session_state[key]]
    memory[area_type] = chosen
    return chosen


# Slider for choosing which weeks of data to use
def period_selector(page, dates):
    widget_key = f"{page}_period"
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
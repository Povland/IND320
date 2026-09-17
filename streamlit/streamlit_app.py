import streamlit as st
import random


#initialization
if 'randome_num' not in st.session_state:
    st.session_state.randome_num = None
if 'counter' not in st.session_state:
    st.session_state.counter = 0
if 'oddEvenStatus' not in st.session_state:
    st.session_state.oddEvenStatus = None
if 'button_name' not in st.session_state:
    st.session_state.button_name = "Start"

def increment():
    if (st.session_state.counter == 0):
        st.session_state.randome_num = random.randint(1, 100)
        st.session_state.counter += 1
    else:
        st.session_state.counter += 1
        if (st.session_state.randome_num == None):
            st.error("session state != 1 + randome_num == None")
        
        if (st.session_state.randome_num % 2 == 0):
            #if even
            st.session_state.button_name = "Half it"
            st.session_state.oddEvenStatus = "Even"
            st.session_state.randome_num = st.session_state.randome_num // 2
        elif (st.session_state.randome_num % 2 != 0):
            #if odd
            st.session_state.button_name = "Triple it and add 1"
            st.session_state.oddEvenStatus = "Odd"
            st.session_state.randome_num = st.session_state.randome_num * 3
            st.session_state.randome_num += 1

    
            



st.button(st.session_state.button_name, on_click=increment)

if (st.session_state.oddEvenStatus != None):
    st.write(f"{st.session_state.oddEvenStatus}")
st.write(f"Randome number {st.session_state.randome_num}")
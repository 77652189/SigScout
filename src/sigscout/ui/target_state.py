from __future__ import annotations

import re

import streamlit as st


FUSION_TARGET_SESSION_KEY = "fusion_target_key"


def target_state_key(name: str, target_key: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name).strip()).strip("_.-")
    safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(target_key).strip()).strip("_.-")
    return f"{safe_name or 'state'}_{(safe_target or 'target').lower()}"


def prepare_target_selector(
    widget_scope: str,
    options: list[str] | tuple[str, ...],
    default: str = "opn",
) -> str:
    valid_options = tuple(options)
    fallback = default if default in valid_options else valid_options[0]
    current = str(st.session_state.get(FUSION_TARGET_SESSION_KEY, fallback))
    if current not in valid_options:
        current = fallback
    st.session_state[FUSION_TARGET_SESSION_KEY] = current
    widget_key = target_state_key("fusion_target_widget", widget_scope)
    st.session_state[widget_key] = current
    return widget_key


def commit_target_selector(
    widget_key: str,
    options: list[str] | tuple[str, ...],
    default: str = "opn",
) -> None:
    valid_options = tuple(options)
    fallback = default if default in valid_options else valid_options[0]
    selected = str(st.session_state.get(widget_key, fallback))
    st.session_state[FUSION_TARGET_SESSION_KEY] = selected if selected in valid_options else fallback

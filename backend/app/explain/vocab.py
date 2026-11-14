"""Shared word lists: variable aliases, direction, certainty and jargon patterns.

Plain data, no logic. Used by the keyword router and the narrative validator.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# How a 14-year-old (or the LLM) may name each catalog variable in prose.
VARIABLE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "grace_tws": ("total water", "water stored", "stored water", "water storage", "groundwater", "water"),
    "t2m": ("air temperature", "temperature"),
    "precip": ("rainfall", "rain", "precipitation"),
    "solar": ("sunlight", "sunshine", "solar"),
    "ndvi": ("plant greenness", "greenness", "vegetation", "plants", "green"),
    "lst_day": ("ground temperature", "surface temperature", "land temperature"),
    "et": ("evaporat", "evapotranspiration"),
    "snow_cover": ("snow cover", "snow"),
    "soil_moisture": ("soil moisture", "topsoil", "soil"),
    "runoff": ("runoff", "run-off"),
    "water_area": ("open-water area", "open water", "water area", "water surface", "shoreline"),
}

# Plain-language topics -> variables, for the no-LLM keyword router.
TOPIC_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "lake": ("grace_tws", "water_area", "precip", "runoff"),
    "reservoir": ("grace_tws", "water_area", "precip", "runoff"),
    "dry": ("grace_tws", "water_area", "precip", "soil_moisture"),
    "drought": ("grace_tws", "precip", "soil_moisture"),
    "wetland": ("water_area", "grace_tws", "precip", "soil_moisture", "ndvi"),
    "shrink": ("water_area", "grace_tws"),
    "river": ("runoff", "precip", "grace_tws"),
    "flood": ("runoff", "precip"),
    "hot": ("t2m", "lst_day"),
    "heat": ("t2m", "lst_day"),
    "warm": ("t2m", "lst_day"),
    "cold": ("t2m",),
    "climate": ("t2m", "precip", "solar"),
    "glacier": ("snow_cover", "grace_tws", "t2m"),
    "ice": ("snow_cover", "grace_tws", "t2m"),
    "melt": ("snow_cover", "grace_tws", "t2m"),
    "tree": ("ndvi",),
    "forest": ("ndvi",),
    "crop": ("ndvi", "et"),
    "farm": ("ndvi", "et", "grace_tws"),
    "sun": ("solar",),
    "cloud": ("solar",),
}

UNKNOWN_ID = "unknown"

_UP = (
    r"ris(?:e|es|ing|en)", r"rose", r"increas(?:e|es|ed|ing)", r"grow(?:s|ing|n)?", r"grew",
    r"go(?:es|ing)? up", r"gone up", r"went up", r"climb(?:s|ed|ing)?", r"higher",
    r"warm(?:er|ing)", r"hotter", r"gain(?:s|ed|ing)?", r"up by", r"more and more", r"wetter",
)
_DOWN = (
    r"fall(?:s|ing|en)?", r"fell", r"drop(?:s|ped|ping)?", r"decreas(?:e|es|ed|ing)",
    r"declin(?:e|es|ed|ing)", r"shrink(?:s|ing)?", r"shrank", r"go(?:es|ing)? down", r"gone down",
    r"went down", r"lower", r"cool(?:er|ing)", r"colder", r"dr(?:ying|ied|ier)", r"los(?:e|es|ing|t)",
    r"down by", r"sink(?:s|ing)?", r"sank", r"less and less", r"emptying",
)
UP_WORDS = re.compile(r"\b(?:" + "|".join(_UP) + r")\b", re.IGNORECASE)
DOWN_WORDS = re.compile(r"\b(?:" + "|".join(_DOWN) + r")\b", re.IGNORECASE)

# Certainty a non-"real" verdict cannot carry.
CERTAINTY_WORDS = re.compile(
    r"\b(?:definitely|certainly|clearly|surely|undeniabl[ey]|guaranteed?|confirmed|"
    r"for sure|for real|without (?:a |any )?doubt|no doubt|100 ?%)",
    re.IGNORECASE,
)
# "Proof" language is never allowed: the residual is a lead, never proof.
PROOF_WORDS = re.compile(r"\b(?:prov(?:e|es|ed|en|ing)|proof)\b", re.IGNORECASE)
NEGATED_PROOF = re.compile(
    r"\b(?:not|no|isn'?t|is not|never|without)\s+(?:a\s+|any\s+)?(?:proof|prov(?:e|es|ed|en|ing))\b",
    re.IGNORECASE,
)
# Causal claims are only allowed when hedged.
CAUSAL_WORDS = re.compile(r"\b(?:caused by|is causing|are causing|the reason is|is due to|are due to|because of (?:people|humans))\b", re.IGNORECASE)
HEDGE_WORDS = re.compile(r"\b(?:could|might|may|maybe|perhaps|possibly|not|can'?t|cannot)\b", re.IGNORECASE)

JARGON_WORDS = re.compile(
    r"\b(?:mann[- ]?kendall|fdr|false discovery|p[- ]?values?|q[- ]?values?|sen'?s slope|"
    r"statistical(?:ly)?|significan(?:t|ce)|regression|residuals?|benjamini|hochberg|"
    r"confidence interval|standard deviation|sigma|hamed|rao|de-?seasonali[sz]ed?)\b",
    re.IGNORECASE,
)

LEAD_PHRASE = re.compile(r"\ba lead,? not (?:a )?proof\b", re.IGNORECASE)

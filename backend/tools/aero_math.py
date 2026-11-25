"""
backend/tools/aero_math.py
─────────────────────────────────────────────────────────────────
Deterministic Avionics Math Tool for AeroMind 2.0 (PLAN §7.6, Task 1.8).
Refactored from agent_orchestrator.py:31-177 (QW5).
Performs deterministic physics, Mach conversions, and fuel flow calculations
without SLM hallucinations or invented default inputs.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from config import settings


class AvionicsMathEngine:
    """
    Deterministic math and physics engine to prevent SLM calculation hallucinations.
    Handles Mach, fuel flow, descent rates, altitude atmospheric models, and unit conversions.
    """

    @staticmethod
    def calculate(query: str) -> Optional[Dict[str, Any]]:
        query_lower = query.lower()
        has_math = any(
            w in query_lower
            for w in [
                "calculate",
                "fuel",
                "burn",
                "mach",
                "speed",
                "consumption",
                "distance",
                "range",
                "convert",
                "endurance",
                "kg",
                "lbs",
                "altitude",
                "descent",
                "time",
                "tas",
            ]
        )

        if not has_math:
            return None

        numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", query)]
        results = {}
        missing_inputs: List[str] = []

        # 1. Mach to True Airspeed calculation
        mach_match = re.search(r"mach\s*(\d+(?:\.\d+)?)", query_lower)
        if mach_match:
            m_val = float(mach_match.group(1))
            alt_m = None
            alt_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|meters?|metres?)\b", query_lower)
            ft_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|foot)\b", query_lower)
            if alt_match:
                alt_m = float(alt_match.group(1))
            elif ft_match:
                alt_m = round(float(ft_match.group(1)) * 0.3048, 1)

            if alt_m is None:
                missing_inputs.append("altitude")
                results["mach_speed"] = {
                    "mach": m_val,
                    "missing_inputs": ["altitude"],
                    "formula": f"TAS for Mach {m_val} not computed: the altitude was not given (speed of sound depends on altitude).",
                }
            else:
                temp_k = max(216.65, 288.15 - (0.0065 * alt_m))
                speed_of_sound_kmh = 3.6 * math.sqrt(1.4 * 287.05 * temp_k)
                tas_kmh = round(m_val * speed_of_sound_kmh, 1)
                tas_knots = round(tas_kmh / 1.852, 1)

                results["mach_speed"] = {
                    "mach": m_val,
                    "altitude_m": alt_m,
                    "tas_kmh": tas_kmh,
                    "tas_knots": tas_knots,
                    "formula": f"TAS = Mach ({m_val}) × a({alt_m}m, ISA) = {tas_kmh} km/h ({tas_knots} knots)",
                }

        # 2. Fuel Burn / Endurance Calculation
        if "fuel" in query_lower and ("burn" in query_lower or "endurance" in query_lower or "consumption" in query_lower):
            is_afterburner = "afterburner" in query_lower or "reheat" in query_lower or "emergency power" in query_lower
            mode = "AFTERBURNER" if is_afterburner else "CRUISE"
            fuel_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilos?|kilograms?)\b", query_lower)
            if not fuel_match:
                missing_inputs.append("fuel_quantity_kg")
                results["fuel_endurance"] = {
                    "mode": mode,
                    "missing_inputs": ["fuel_quantity_kg"],
                    "formula": "Fuel endurance not computed: the fuel quantity (in kg) was not given.",
                }
            else:
                fuel_kg = float(fuel_match.group(1))
                burn_rate_kg_min = (
                    settings.FUEL_BURN_AFTERBURNER_KG_MIN if is_afterburner else settings.FUEL_BURN_CRUISE_KG_MIN
                )
                endurance_minutes = round(fuel_kg / burn_rate_kg_min, 1)
                results["fuel_endurance"] = {
                    "fuel_quantity_kg": fuel_kg,
                    "mode": mode,
                    "consumption_rate_kg_min": burn_rate_kg_min,
                    "rate_source": "configured reference rate (not taken from the manual)",
                    "flight_endurance_min": endurance_minutes,
                    "formula": (
                        f"Endurance = {fuel_kg} kg / {burn_rate_kg_min} kg/min = {endurance_minutes} minutes "
                        f"(burn rate is a configured reference value, not from the manual)"
                    ),
                }

        # 3. Unit Conversions
        if "convert" in query_lower or "to lbs" in query_lower or "to kg" in query_lower or "to feet" in query_lower:
            conversions = []
            for num in numbers[:2]:
                if "kg" in query_lower or "lbs" in query_lower:
                    lbs = round(num * 2.20462, 1)
                    kg = round(num / 2.20462, 1)
                    conversions.append(f"{num} kg = {lbs} lbs | {num} lbs = {kg} kg")
                if "meter" in query_lower or "feet" in query_lower or "ft" in query_lower:
                    ft = round(num * 3.28084, 1)
                    m = round(num / 3.28084, 1)
                    conversions.append(f"{num} m = {ft} ft | {num} ft = {m} m")
                if "km/h" in query_lower or "knot" in query_lower:
                    kn = round(num / 1.852, 1)
                    kmh = round(num * 1.852, 1)
                    conversions.append(f"{num} km/h = {kn} knots | {num} knots = {kmh} km/h")
            if conversions:
                results["conversions"] = conversions

        if not results:
            return None

        summary_lines = []
        for k, v in results.items():
            if isinstance(v, dict) and "formula" in v:
                summary_lines.append(f"• {v['formula']}")
            elif isinstance(v, dict) and "conversions" in v:
                summary_lines.extend([f"• {c}" for c in v["conversions"]])
            elif isinstance(v, list):
                summary_lines.extend([f"• {item}" for item in v])

        return {
            "metrics": results,
            "summary_text": "\n".join(summary_lines),
            "missing_inputs": missing_inputs,
            "deterministic": True,
        }

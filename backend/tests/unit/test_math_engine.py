"""QW5: the deterministic math tool never invents inputs."""
from agent_orchestrator import AvionicsMathEngine as M


def test_fuel_consumption_without_quantity_gives_no_number():
    res = M.calculate("what is the fuel consumption of the engine")
    assert res is not None
    fe = res["metrics"]["fuel_endurance"]
    assert "flight_endurance_min" not in fe
    assert fe["missing_inputs"] == ["fuel_quantity_kg"]
    assert "2800" not in res["summary_text"]


def test_minutes_are_not_read_as_altitude():
    res = M.calculate("mach 2 for 5 minutes")
    ms = res["metrics"]["mach_speed"]
    assert ms.get("altitude_m") != 5.0
    assert ms["missing_inputs"] == ["altitude"]
    assert "tas_kmh" not in ms


def test_explicit_inputs_still_compute():
    tas = M.calculate("Calculate TAS for Mach 1.6 at 11000m")["metrics"]["mach_speed"]
    assert tas["altitude_m"] == 11000.0 and tas["tas_kmh"] == 1699.6
    fuel = M.calculate("Calculate fuel endurance for 2400 kg with afterburner")["metrics"]["fuel_endurance"]
    assert fuel["flight_endurance_min"] == 8.6
    assert "not taken from the manual" in fuel["rate_source"]


def test_feet_altitude_converted():
    tas = M.calculate("Mach 0.8 at 36000 ft")["metrics"]["mach_speed"]
    assert tas["altitude_m"] == round(36000 * 0.3048, 1)


def test_litres_are_not_treated_as_kilograms():
    fe = M.calculate("fuel endurance with 2000 liters")["metrics"]["fuel_endurance"]
    assert fe["missing_inputs"] == ["fuel_quantity_kg"]

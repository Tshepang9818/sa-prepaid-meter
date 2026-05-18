import os
import time
import random
import requests
from datetime import datetime

API_URL = os.getenv("API_URL", "http://app:8000")

SA_HOUSEHOLDS = [
    {
        "name": "Nkosi Family",
        "address": "12 Vilakazi St, Soweto",
        "province": "Gauteng",
        "phone": "+27821234561",
        "meter_number": "MTR001",
        "units_remaining": 50.0
    },
    {
        "name": "Dlamini Family",
        "address": "45 Main Rd, Umlazi",
        "province": "KwaZulu-Natal",
        "phone": "+27821234562",
        "meter_number": "MTR002",
        "units_remaining": 15.0
    },
    {
        "name": "Mokoena Family",
        "address": "8 Church St, Mamelodi",
        "province": "Gauteng",
        "phone": "+27821234563",
        "meter_number": "MTR003",
        "units_remaining": 35.0
    },
    {
        "name": "Botha Family",
        "address": "23 Oak Ave, Stellenbosch",
        "province": "Western Cape",
        "phone": "+27821234564",
        "meter_number": "MTR004",
        "units_remaining": 80.0
    },
    {
        "name": "Zulu Family",
        "address": "67 King St, Durban CBD",
        "province": "KwaZulu-Natal",
        "phone": "+27821234565",
        "meter_number": "MTR005",
        "units_remaining": 8.0
    },
    {
        "name": "Pietersen Family",
        "address": "34 Rose St, Mitchell's Plain",
        "province": "Western Cape",
        "phone": "+27821234566",
        "meter_number": "MTR006",
        "units_remaining": 45.0
    },
    {
        "name": "Molefe Family",
        "address": "89 Freedom St, Polokwane",
        "province": "Limpopo",
        "phone": "+27821234567",
        "meter_number": "MTR007",
        "units_remaining": 25.0
    },
    {
        "name": "Hendricks Family",
        "address": "15 Voortrekker Rd, Bloemfontein",
        "province": "Free State",
        "phone": "+27821234568",
        "meter_number": "MTR008",
        "units_remaining": 60.0
    },
    {
        "name": "Sithole Family",
        "address": "56 New Rd, Khayelitsha",
        "province": "Western Cape",
        "phone": "+27821234569",
        "meter_number": "MTR009",
        "units_remaining": 12.0
    },
    {
        "name": "Van Wyk Family",
        "address": "3 Palm St, Pretoria North",
        "province": "Gauteng",
        "phone": "+27821234570",
        "meter_number": "MTR010",
        "units_remaining": 90.0
    }
]

APPLIANCE_PROFILES = {
    "geyser":          {"morning": 0.8, "midday": 0.1, "evening": 0.7, "night": 0.0},
    "stove":           {"morning": 0.6, "midday": 0.3, "evening": 0.8, "night": 0.0},
    "fridge":          {"morning": 1.0, "midday": 1.0, "evening": 1.0, "night": 1.0},
    "tv":              {"morning": 0.2, "midday": 0.1, "evening": 0.9, "night": 0.0},
    "washing_machine": {"morning": 0.5, "midday": 0.3, "evening": 0.2, "night": 0.0}
}

registered_households = {}

def get_time_period():
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "morning"
    elif 10 <= hour < 17:
        return "midday"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "night"

def wait_for_api():
    print(f"Waiting for API at {API_URL}...")
    retries = 30
    while retries > 0:
        try:
            response = requests.get(f"{API_URL}/health", timeout=5)
            if response.status_code == 200:
                print("API is ready")
                return True
        except Exception:
            pass
        print(f"API not ready, retrying in 10s... ({retries} left)")
        retries -= 1
        time.sleep(10)
    return False

def register_all_households():
    print("Registering all SA households...")
    for household in SA_HOUSEHOLDS:
        try:
            existing = requests.get(f"{API_URL}/households", timeout=5)
            households_list = existing.json()
            already_registered = any(
                h["meter_number"] == household["meter_number"]
                for h in households_list
            )
            if already_registered:
                matching = next(
                    h for h in households_list
                    if h["meter_number"] == household["meter_number"]
                )
                registered_households[household["meter_number"]] = matching["id"]
                print(f"Already registered: {household['name']}")
                continue
            response = requests.post(
                f"{API_URL}/households",
                json=household,
                timeout=5
            )
            if response.status_code == 200:
                household_id = response.json()["household_id"]
                registered_households[household["meter_number"]] = household_id
                print(f"Registered: {household['name']} — ID {household_id}")
            else:
                print(f"Failed to register {household['name']}: {response.text}")
        except Exception as e:
            print(f"Error registering {household['name']}: {e}")
        time.sleep(0.5)

def send_reading(household_id: int, household_name: str):
    period = get_time_period()
    appliance_choices = []
    for appliance, profile in APPLIANCE_PROFILES.items():
        probability = profile[period]
        if random.random() < probability:
            appliance_choices.append(appliance)
    if not appliance_choices:
        appliance_choices = ["fridge"]
    appliance = random.choice(appliance_choices)
    if appliance == "fridge":
        duration = round(random.uniform(0.1, 0.5), 2)
    elif appliance == "geyser":
        duration = round(random.uniform(0.5, 2.0), 2)
    elif appliance == "stove":
        duration = round(random.uniform(0.3, 1.5), 2)
    elif appliance == "tv":
        duration = round(random.uniform(0.5, 3.0), 2)
    else:
        duration = round(random.uniform(0.5, 1.5), 2)
    try:
        response = requests.post(
            f"{API_URL}/readings",
            json={
                "household_id": household_id,
                "appliance": appliance,
                "duration_hours": duration
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts_triggered", [])
            alert_str = f" ⚠ ALERTS: {alerts}" if alerts else ""
            print(
                f"{household_name} | {appliance} | "
                f"{duration}h | R{data['cost_zar']} | "
                f"{data['units_remaining']} units left{alert_str}"
            )
        else:
            print(f"Reading failed for {household_name}: {response.text}")
    except Exception as e:
        print(f"Error sending reading for {household_name}: {e}")

def run_simulator():
    if not wait_for_api():
        print("API never became ready. Exiting.")
        return
    register_all_households()
    print(f"\nSimulator running — generating readings every 5 seconds")
    print(f"Current time period: {get_time_period()}\n")
    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Cycle {cycle} | {datetime.now().strftime('%H:%M:%S')} | Period: {get_time_period()} ---")
        for meter_number, household_id in registered_households.items():
            household_name = next(
                h["name"] for h in SA_HOUSEHOLDS
                if h["meter_number"] == meter_number
            )
            send_reading(household_id, household_name)
            time.sleep(0.3)
        time.sleep(5)

if __name__ == "__main__":
    run_simulator()

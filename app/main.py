import os
import time
import json
import psycopg2
import redis
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="SA Prepaid Meter Monitor API")
Instrumentator().instrument(app).expose(app)

DB_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
AT_API_KEY = os.getenv("AT_API_KEY")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_SENDER_ID = os.getenv("AT_SENDER_ID", "METER")

cache = redis.from_url(REDIS_URL, decode_responses=True)

APPLIANCES = ["geyser", "stove", "fridge", "tv", "washing_machine"]

ESKOM_RATE_PER_KWH = 2.31

LOW_UNITS_THRESHOLD = 10.0
GEYSER_HOURS_THRESHOLD = 4.0

APPLIANCE_WATTS = {
    "geyser": 3000,
    "stove": 2000,
    "fridge": 150,
    "tv": 100,
    "washing_machine": 500
}

def get_conn():
    return psycopg2.connect(DB_URL)

def init_db():
    retries = 5
    while retries > 0:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS households (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    address TEXT NOT NULL,
                    province TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    meter_number TEXT UNIQUE NOT NULL,
                    units_remaining FLOAT DEFAULT 50.0,
                    registered_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id SERIAL PRIMARY KEY,
                    household_id INTEGER REFERENCES households(id),
                    appliance TEXT NOT NULL,
                    watts FLOAT NOT NULL,
                    kwh FLOAT NOT NULL,
                    cost_zar FLOAT NOT NULL,
                    duration_hours FLOAT NOT NULL,
                    recorded_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    household_id INTEGER REFERENCES households(id),
                    alert_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    sent_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()
            conn.close()
            print("Database initialised successfully")
            break
        except Exception as e:
            print(f"DB not ready, retrying in 5s... ({e})")
            retries -= 1
            time.sleep(5)

init_db()

class Household(BaseModel):
    name: str
    address: str
    province: str
    phone: str
    meter_number: str
    units_remaining: float = 50.0

class Reading(BaseModel):
    household_id: int
    appliance: str
    duration_hours: float

class TopupRequest(BaseModel):
    household_id: int
    units: float

def send_sms(phone: str, message: str) -> bool:
    try:
        response = requests.post(
            "https://api.africastalking.com/version1/messaging",
            headers={
                "apiKey": AT_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            data={
                "username": AT_USERNAME,
                "to": phone,
                "message": message,
                "from": AT_SENDER_ID
            }
        )
        result = response.json()
        print(f"SMS sent to {phone}: {result}")
        return True
    except Exception as e:
        print(f"SMS failed: {e}")
        return False

def check_and_alert(household_id: int, appliance: str,
                    duration_hours: float, units_remaining: float,
                    phone: str, household_name: str):
    conn = get_conn()
    cur = conn.cursor()
    alerts_sent = []

    if units_remaining <= LOW_UNITS_THRESHOLD:
        message = (
            f"ALERT: {household_name}, your prepaid meter has "
            f"only {units_remaining:.1f} units remaining. "
            f"Please top up urgently to avoid losing power. "
            f"Current cost rate: R{ESKOM_RATE_PER_KWH}/kWh"
        )
        sent = send_sms(phone, message)
        if sent:
            cur.execute("""
                INSERT INTO alerts
                (household_id, alert_type, message, phone)
                VALUES (%s, %s, %s, %s)
            """, (household_id, "LOW_UNITS", message, phone))
            alerts_sent.append("LOW_UNITS")

    if appliance == "geyser" and duration_hours >= GEYSER_HOURS_THRESHOLD:
        message = (
            f"WARNING: {household_name}, your geyser has been "
            f"running for {duration_hours:.1f} hours. "
            f"This uses approximately "
            f"R{(APPLIANCE_WATTS['geyser']/1000) * duration_hours * ESKOM_RATE_PER_KWH:.2f} "
            f"worth of electricity. Consider switching it off."
        )
        sent = send_sms(phone, message)
        if sent:
            cur.execute("""
                INSERT INTO alerts
                (household_id, alert_type, message, phone)
                VALUES (%s, %s, %s, %s)
            """, (household_id, "GEYSER_WARNING", message, phone))
            alerts_sent.append("GEYSER_WARNING")

    conn.commit()
    conn.close()
    return alerts_sent

@app.get("/")
def root():
    return {
        "service": "SA Prepaid Meter Monitor",
        "status": "running",
        "eskom_rate_per_kwh": ESKOM_RATE_PER_KWH,
        "appliances_tracked": APPLIANCES
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": str(datetime.utcnow())
    }

@app.post("/households")
def register_household(household: Household):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO households
            (name, address, province, phone, meter_number, units_remaining)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (household.name, household.address, household.province,
              household.phone, household.meter_number,
              household.units_remaining))
        household_id = cur.fetchone()[0]
        conn.commit()
        cache.delete("all_households")
        return {
            "message": "Household registered",
            "household_id": household_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.get("/households")
def list_households():
    cached = cache.get("all_households")
    if cached:
        print("Serving households from Redis cache")
        return json.loads(cached)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, address, province, phone,
               meter_number, units_remaining, registered_at
        FROM households ORDER BY registered_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    result = [
        {
            "id": r[0], "name": r[1], "address": r[2],
            "province": r[3], "phone": r[4],
            "meter_number": r[5], "units_remaining": r[6],
            "registered_at": str(r[7])
        } for r in rows
    ]
    cache.setex("all_households", 30, json.dumps(result))
    return result

@app.post("/readings")
def submit_reading(reading: Reading):
    if reading.appliance not in APPLIANCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown appliance. Must be one of: {APPLIANCES}"
        )
    watts = APPLIANCE_WATTS[reading.appliance]
    kwh = (watts / 1000) * reading.duration_hours
    cost_zar = kwh * ESKOM_RATE_PER_KWH
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, phone, units_remaining FROM households
        WHERE id = %s
    """, (reading.household_id,))
    household = cur.fetchone()
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")
    household_name, phone, current_units = household
    new_units = max(0, current_units - kwh)
    cur.execute("""
        UPDATE households SET units_remaining = %s
        WHERE id = %s
    """, (new_units, reading.household_id))
    cur.execute("""
        INSERT INTO readings
        (household_id, appliance, watts, kwh, cost_zar, duration_hours)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (reading.household_id, reading.appliance,
          watts, kwh, cost_zar, reading.duration_hours))
    reading_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    cache.delete(f"readings_{reading.household_id}")
    cache.delete("all_households")
    alerts = check_and_alert(
        reading.household_id, reading.appliance,
        reading.duration_hours, new_units, phone, household_name
    )
    return {
        "reading_id": reading_id,
        "appliance": reading.appliance,
        "kwh": round(kwh, 4),
        "cost_zar": round(cost_zar, 2),
        "units_remaining": round(new_units, 2),
        "alerts_triggered": alerts
    }

@app.get("/readings/{household_id}")
def get_readings(household_id: int):
    cache_key = f"readings_{household_id}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT appliance, watts, kwh, cost_zar,
               duration_hours, recorded_at
        FROM readings WHERE household_id = %s
        ORDER BY recorded_at DESC LIMIT 100
    """, (household_id,))
    rows = cur.fetchall()
    conn.close()
    result = [
        {
            "appliance": r[0], "watts": r[1],
            "kwh": r[2], "cost_zar": r[3],
            "duration_hours": r[4], "recorded_at": str(r[5])
        } for r in rows
    ]
    cache.setex(cache_key, 30, json.dumps(result))
    return result

@app.get("/consumption/top")
def top_consumption():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.appliance,
               SUM(r.kwh) as total_kwh,
               SUM(r.cost_zar) as total_cost_zar,
               COUNT(*) as reading_count,
               h.province
        FROM readings r
        JOIN households h ON r.household_id = h.id
        GROUP BY r.appliance, h.province
        ORDER BY total_kwh DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "appliance": r[0],
            "total_kwh": round(r[1], 2),
            "total_cost_zar": round(r[2], 2),
            "reading_count": r[3],
            "province": r[4]
        } for r in rows
    ]

@app.post("/topup")
def topup_units(topup: TopupRequest):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE households
        SET units_remaining = units_remaining + %s
        WHERE id = %s RETURNING units_remaining, name
    """, (topup.units, topup.household_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Household not found")
    conn.commit()
    conn.close()
    cache.delete("all_households")
    return {
        "message": f"Topped up {topup.units} units",
        "new_balance": round(row[0], 2),
        "household": row[1]
    }

@app.get("/alerts")
def get_alerts():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.alert_type, a.message, a.phone,
               a.sent_at, h.name, h.province
        FROM alerts a
        JOIN households h ON a.household_id = h.id
        ORDER BY a.sent_at DESC LIMIT 100
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "alert_type": r[0], "message": r[1],
            "phone": r[2], "sent_at": str(r[3]),
            "household": r[4], "province": r[5]
        } for r in rows
    ]

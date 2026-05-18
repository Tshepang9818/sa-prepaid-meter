# SA Prepaid Meter Monitor

A DevOps pipeline that simulates prepaid electricity meters across
South African households, tracks appliance consumption in real time,
and sends SMS alerts via Africa's Talking when units run critically
low or a geyser runs unusually long.

## The Problem
Over 6 million South African households use prepaid electricity meters.
Running out of units at midnight is not just inconvenient — for families
relying on electric stoves, medical equipment, or home businesses it is
a genuine crisis. This system gives households visibility into their
consumption before it becomes a crisis.

## What It Does
- Simulates 5 appliances per household (geyser, stove, fridge, TV, washing machine)
- Tracks consumption in kWh and cost in ZAR at Eskom tariffs
- Detects which appliance consumes the most power
- Sends SMS alert when units drop below 10
- Sends SMS warning when geyser runs more than 4 hours straight
- Exposes live Grafana dashboards per household per appliance

## Architecture
Simulator → FastAPI → PostgreSQL + Redis
                ↓
         Africa's Talking SMS
                ↓
      Prometheus + Grafana
                ↓
    Kubernetes k3s (orchestration)
                ↓
     GitHub Actions (CI/CD)

## Stack
- Python / FastAPI     — meter reading REST API
- PostgreSQL           — persistent meter and alert storage
- Redis                — consumption cache
- Docker               — containerisation
- Kubernetes k3s       — orchestration and autoscaling
- GitHub Actions       — CI/CD pipeline
- Prometheus + Grafana — live consumption dashboards
- Africa's Talking     — SMS alerts to households

## Run locally
cp .env.example .env
docker compose up --build
curl http://localhost:8014/health

## Endpoints
GET  /health                    health check
POST /households                register a household meter
GET  /households                list all households
POST /readings                  submit a meter reading
GET  /readings/{household_id}   get readings for a household
GET  /consumption/top           top consuming appliances across all households
GET  /alerts                    all SMS alerts sent

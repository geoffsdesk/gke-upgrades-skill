To fulfill your company's schedule, we must combine **Maintenance Exclusions** (for June and Black Friday/Cyber Monday) with **Static Versioning** (to permanently prevent automatic minor upgrades). 

Here is the exact configuration, along with the architectural reasoning behind how GKE handles these specific rules.

### The Strategy & GKE Limitations
1. **The June Freeze & Black Friday:** We will use `NO_UPGRADES` maintenance exclusions. GKE strictly limits `NO_UPGRADES` blocks to a **maximum of 30 days**. June 1st to June 30th is exactly 30 days, which fits perfectly. Black Friday/Cyber Monday dates shift yearly, so we will block a safe 20-day window (Nov 15 -
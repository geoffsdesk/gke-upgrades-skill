In a SOX-compliant, financial services environment, predictability and auditability are just as important as the configuration itself. Because you are dealing with strict change-management controls, **Infrastructure as Code (IaC) is highly recommended** over manual clicks or CLI commands. 

Below is the strategy and the exact configuration (provided in Terraform, the industry standard for IaC, as well as `gcloud` CLI) to achieve your requirements.

### ⚠️ Crucial GKE Compliance Limits to Note First
Google Cloud imposes strict limits on Maintenance Exclusions to ensure clusters don't fall dangerously behind on security patches:
1. **90-Day Limit:** You can only use the `NO_UPGRADES` scope for a maximum of **90 days** in a rolling 365-day window. 
2. **30-Day Limit:** A single exclusion cannot exceed 30 continuous days.
3. **Emergency Bypasses:** If a critical zero-day vulnerability occurs (e.g., CVSS 9.0+), Google *reserves the right* to bypass your exclusion to secure the infrastructure. Your auditors should be aware of this cloud-native shared-responsibility nuance.

---

### Phase 1: The Configuration Strategy
1. **Release Channel:** Set to **Stable**. This ensures you only get updates that have baked in the Rapid and Regular channels for months.
2. **Maintenance Window:** A recurring 48-hour window starting Saturday 00:00 UTC to Sunday 23:59 UTC.
3. **Exclusion 1 (Annual Audit):** A block in November (e.g., Nov 1 to Nov 15).
4. **Exclusion 2 (Quarterly Freezes):** Blocks at the end of Q1, Q2, Q3, and Q4 (e.g., the last 7 days of the quarter).

*Total exclusion days in this example: 14 (Audit) + 28 (Quarterly) = 42 days (Safely under the 90-day limit).*

---

### Phase 2: Terraform Implementation (Recommended for SOX)
For a multi-cluster setup, you should define this in a Terraform module and apply it across your 3 clusters. Note: **All times must be in UTC.**

```hcl
resource "google_container_cluster" "primary" {
  name     = "fin-prod-cluster-1"
  location = "us-central1"

  # 1. Enforce Stable Release Channel
  release_channel {
    channel = "STABLE"
  }

  maintenance_policy {
    # 2. Weekend-Only Maintenance Window
    # Starts Saturday at 00:00 UTC, runs for 48 hours.
    recurring_window {
      start_time = "2024-01-06T00:00:00Z" # Must be a valid past/future Saturday
      end_time   = "2024-01-08T00:00:00Z" # Must be exactly 48 hours later
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }

    # 3. Annual November Audit Exclusion (e.g., Nov 1 - Nov 15)
    maintenance_exclusion {
      exclusion_name = "annual-sox-audit-nov"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-15T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # 4. Quarterly Code Freezes (Example: Last 7 days of quarters)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze"
      start_time     = "2024-03-25T00:00:00Z"
      end_time       = "2024-03-31T23:59:59Z"
      exclusion_options { scope = "NO_UPGRADES" }
    }

    maintenance_exclusion {
      exclusion_name = "q2-code-freeze"
      start_time     = "2024-06-24T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options { scope = "NO_UPGRADES" }
    }

    maintenance_exclusion {
      exclusion_name = "q3-code-freeze"
      start_time     = "2024-09-24T00:00:00Z"
      end_time       = "2024-09-30T23:59:59Z"
      exclusion_options { scope = "NO_UPGRADES" }
    }

    maintenance_exclusion {
      exclusion_name = "q4-code-freeze"
      start_time     = "2024-12-25T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_options { scope = "NO_UPGRADES" }
    }
  }
}
```

---

### Alternative: `gcloud` CLI Implementation
If you need to apply this immediately while building your IaC, use the following commands. You will need to run these against all 3 clusters.

**1. Set the weekend maintenance window:**
```bash
gcloud container clusters update CLUSTER_NAME \
    --region=COMPUTE_REGION \
    --maintenance-window-start="2024-01-06T00:00:00Z" \
    --maintenance-window-end="2024-01-08T00:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU"
```

**2. Add the November Audit Exclusion:**
```bash
gcloud container clusters update CLUSTER_NAME \
    --region=COMPUTE_REGION \
    --add-maintenance-exclusion-name="annual-sox-audit-nov" \
    --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-11-15T23:59:59Z" \
    --add-maintenance-exclusion-scope="no_upgrades"
```

*(Repeat step 2 for the Q1, Q2, Q3, and Q4 dates, changing the name and date parameters accordingly).*

---

### SOX/Financial Best Practices to Implement Alongside This:

1. **Pub/Sub Upgrade Notifications:** Auditors will want proof of when updates actually happen. Enable [GKE cluster notifications](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-notifications) to send upgrade events to a Pub/Sub topic, which can then trigger a Jira/ServiceNow ticket for your Change Approval Board (CAB) records.
2. **Cloud Audit Logs:** Ensure Admin Activity and Data Access audit logs are enabled and routed to a tamper-proof log sink (like a locked-down BigQuery dataset or a hardened SIEM) with a strict retention policy (usually 1-7 years for financials).
3. **Exclusion Expiration Operations:** Maintenance exclusions do *not* recur annually. You must update the dates in your Terraform code every year. I recommend adding a calendar alert for your DevOps team in early January to update the IaC for the new year's dates.
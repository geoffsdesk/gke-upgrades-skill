I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive solution:

## 1. Maintenance Window Configuration

First, let's set up weekend-only maintenance windows for your clusters:

```bash
# Configure maintenance window for each cluster (example for cluster 1)
gcloud container clusters update CLUSTER_NAME_1 \
    --zone=YOUR_ZONE \
    --maintenance-window-start "2023-01-07T02:00:00Z" \
    --maintenance-window-end "2023-01-07T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# For cluster 2
gcloud container clusters update CLUSTER_NAME_2 \
    --zone=YOUR_ZONE \
    --maintenance-window-start "2023-01-07T06:00:00Z" \
    --maintenance-window-end "2023-01-07T10:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# For cluster 3 (Sunday maintenance)
gcloud container clusters update CLUSTER_NAME_3 \
    --zone=YOUR_ZONE \
    --maintenance-window-start "2023-01-08T02:00:00Z" \
    --maintenance-window-end "2023-01-08T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## 2. Terraform Configuration for Infrastructure as Code

```hcl
# terraform/gke-maintenance.tf
resource "google_container_cluster" "compliant_clusters" {
  count    = 3
  name     = "prod-cluster-${count.index + 1}"
  location = var.cluster_zones[count.index]

  # Maintenance policy for SOX compliance
  maintenance_policy {
    recurring_window {
      start_time = count.index < 2 ? "2023-01-07T0${2 + count.index * 4}:00:00Z" : "2023-01-08T02:00:00Z"
      end_time   = count.index < 2 ? "2023-01-07T0${6 + count.index * 4}:00:00Z" : "2023-01-08T06:00:00Z"
      recurrence = count.index < 2 ? "FREQ=WEEKLY;BYDAY=SA" : "FREQ=WEEKLY;BYDAY=SU"
    }

    maintenance_exclusion {
      exclusion_name = "q1-code-freeze"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-04-05T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q2-code-freeze"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-07-05T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q3-code-freeze"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-10-05T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "annual-audit-november"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q4-code-freeze"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2025-01-05T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Auto-upgrade configuration
  node_config {
    machine_type = "e2-standard-4"
  }

  node_pool {
    name = "default-pool"
    management {
      auto_repair  = true
      auto_upgrade = true
    }
  }
}

variable "cluster_zones" {
  description = "Zones for the three clusters"
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c"]
}
```

## 3. Automated Maintenance Exclusion Management Script

```bash
#!/bin/bash
# scripts/manage-maintenance-exclusions.sh

set -e

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to add maintenance exclusion
add_exclusion() {
    local cluster=$1
    local zone=$2
    local exclusion_name=$3
    local start_time=$4
    local end_time=$5
    
    echo "Adding exclusion '$exclusion_name' to cluster $cluster..."
    
    gcloud container clusters update "$cluster" \
        --zone="$zone" \
        --add-maintenance-exclusion-name="$exclusion_name" \
        --add-maintenance-exclusion-start="$start_time" \
        --add-maintenance-exclusion-end="$end_time" \
        --add-maintenance-exclusion-scope=NO_UPGRADES
}

# Function to remove expired exclusions
remove_expired_exclusions() {
    local cluster=$1
    local zone=$2
    
    echo "Checking for expired exclusions in cluster $cluster..."
    
    # Get current exclusions and remove expired ones
    gcloud container clusters describe "$cluster" --zone="$zone" --format="json" | \
    jq -r '.maintenancePolicy.exclusions[]? | select(.endTime < now | strftime("%Y-%m-%dT%H:%M:%SZ")) | .name' | \
    while read -r exclusion_name; do
        if [ -n "$exclusion_name" ]; then
            echo "Removing expired exclusion: $exclusion_name"
            gcloud container clusters update "$cluster" \
                --zone="$zone" \
                --remove-maintenance-exclusion="$exclusion_name"
        fi
    done
}

# Add quarterly code freezes and annual audit exclusions for all clusters
for i in "${!CLUSTERS[@]}"; do
    cluster=${CLUSTERS[$i]}
    zone=${ZONES[$i]}
    
    echo "Configuring maintenance exclusions for $cluster..."
    
    # Remove expired exclusions first
    remove_expired_exclusions "$cluster" "$zone"
    
    # Q1 Code Freeze (mid-March to early April)
    add_exclusion "$cluster" "$zone" "q1-code-freeze-$CURRENT_YEAR" \
        "${CURRENT_YEAR}-03-15T00:00:00Z" "${CURRENT_YEAR}-04-05T23:59:59Z"
    
    # Q2 Code Freeze (mid-June to early July)
    add_exclusion "$cluster" "$zone" "q2-code-freeze-$CURRENT_YEAR" \
        "${CURRENT_YEAR}-06-15T00:00:00Z" "${CURRENT_YEAR}-07-05T23:59:59Z"
    
    # Q3 Code Freeze (mid-September to early October)
    add_exclusion "$cluster" "$zone" "q3-code-freeze-$CURRENT_YEAR" \
        "${CURRENT_YEAR}-09-15T00:00:00Z" "${CURRENT_YEAR}-10-05T23:59:59Z"
    
    # Annual Audit (entire November)
    add_exclusion "$cluster" "$zone" "annual-audit-$CURRENT_YEAR" \
        "${CURRENT_YEAR}-11-01T00:00:00Z" "${CURRENT_YEAR}-11-30T23:59:59Z"
    
    # Q4 Code Freeze (mid-December to early January)
    add_exclusion "$cluster" "$zone" "q4-code-freeze-$CURRENT_YEAR" \
        "${CURRENT_YEAR}-12-15T00:00:00Z" "${NEXT_YEAR}-01-05T23:59:59Z"
    
    echo "Completed configuration for $cluster"
    echo "---"
done

echo "All clusters configured with SOX-compliant maintenance windows and exclusions"
```

## 4. Monitoring and Compliance Script

```bash
#!/bin/bash
# scripts/maintenance-compliance-check.sh

set -e

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")

echo "=== GKE Maintenance Compliance Report ===" > compliance-report.txt
echo "Generated: $(date)" >> compliance-report.txt
echo "" >> compliance-report.txt

for i in "${!CLUSTERS[@]}"; do
    cluster=${CLUSTERS[$i]}
    zone=${ZONES[$i]}
    
    echo "Cluster: $cluster (Zone: $zone)" >> compliance-report.txt
    echo "----------------------------------------" >> compliance-report.txt
    
    # Get maintenance policy details
    gcloud container clusters describe "$cluster" --zone="$zone" --format="json" | \
    jq -r '
        "Maintenance Window: " + (.maintenancePolicy.window.recurringWindow.recurrence // "Not configured"),
        "Window Times: " + (.maintenancePolicy.window.recurringWindow.window.startTime // "N/A") + " to " + (.maintenancePolicy.window.recurringWindow.window.endTime // "N/A"),
        "",
        "Active Exclusions:",
        (.maintenancePolicy.exclusions[]? | 
            "- " + .name + " (" + .startTime + " to " + .endTime + ")"
        )
    ' >> compliance-report.txt
    
    echo "" >> compliance-report.txt
done

# Check for upcoming maintenance events
echo "=== Upcoming Maintenance Events ===" >> compliance-report.txt
for i in "${!CLUSTERS[@]}"; do
    cluster=${CLUSTERS[$i]}
    zone=${ZONES[$i]}
    
    echo "Checking $cluster for scheduled maintenance..." >> compliance-report.txt
    gcloud container operations list --filter="targetLink:$cluster AND status:RUNNING" \
        --format="table(name,operationType,startTime,endTime)" >> compliance-report.txt
done

echo "Compliance report generated: compliance-report.txt"
cat compliance-report.txt
```

## 5. Annual Maintenance Schedule Update Script

```bash
#!/bin/bash
# scripts/annual-schedule-update.sh

# This script should be run annually to update maintenance exclusions for the next year

CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Define your quarterly code freeze dates and annual audit month
Q1_START="03-15"
Q1_END="04-05"
Q2_START="06-15" 
Q2_END="07-05"
Q3_START="09-15"
Q3_END="10-05"
Q4_START="12-15"
Q4_NEXT_END="01-05"
AUDIT_MONTH="11"

# Create configuration file for next year's exclusions
cat > "maintenance-exclusions-${NEXT_YEAR}.yaml" << EOF
# Maintenance exclusions for ${NEXT_YEAR}
exclusions:
  - name: "q1-code-freeze-${NEXT_YEAR}"
    start: "${NEXT_YEAR}-${Q1_START}T00:00:00Z"
    end: "${NEXT_YEAR}-${Q1_END}T23:59:59Z"
    
  - name: "q2-code-freeze-${NEXT_YEAR}"
    start: "${NEXT_YEAR}-${Q2_START}T00:00:00Z"
    end: "${NEXT_YEAR}-${Q2_END}T23:59:59Z"
    
  - name: "q3-code-freeze-${NEXT_YEAR}"
    start: "${NEXT_YEAR}-${Q3_START}T00:00:00Z"
    end: "${NEXT_YEAR}-${Q3_END}T23:59:59Z"
    
  - name: "annual-audit-${NEXT_YEAR}"
    start: "${NEXT_YEAR}-${AUDIT_MONTH}-01T00:00:00Z"
    end: "${NEXT_YEAR}-${AUDIT_MONTH}-30T23:59:59Z"
    
  - name: "q4-code-freeze-${NEXT_YEAR}"
    start: "${NEXT_YEAR}-${Q4_START}T00:00:00Z"
    end: "$((NEXT_YEAR + 1))-${Q4_NEXT_END}T23:59:59Z"
EOF

echo "Generated maintenance exclusions configuration for ${NEXT_YEAR}"
echo "File: maintenance-exclusions-${NEXT_YEAR}.yaml"
```

## 6. Setup Instructions

1. **Make scripts executable:**
```bash
chmod +x scripts/*.sh
```

2. **Run initial setup:**
```bash
./scripts/manage-maintenance-exclusions.sh
```

3. **Set up cron jobs for automation:**
```bash
# Add to crontab (crontab -e)
# Check compliance weekly on Friday
0 9 * * 5 /path/to/scripts/maintenance-compliance-check.sh

# Update annual exclusions every January 1st
0 0 1 1 * /path/to/scripts/annual-schedule-update.sh

# Cleanup expired exclusions monthly
0 2 1 * * /path/to/scripts/manage-maintenance-exclusions.sh
```

## 7. SOX Compliance Features

This configuration provides:

- ✅ **Predictable maintenance windows** (weekends only)
- ✅ **Documented exclusion periods** for audits and code freezes
- ✅ **Automated compliance reporting**
- ✅ **Infrastructure as Code** (Terraform)
- ✅ **Audit trails** through gcloud logging
- ✅ **Change control** through scripted management

The maintenance windows are staggered across Saturday and Sunday to ensure not all clusters update simultaneously, and all critical business periods are protected with maintenance exclusions.
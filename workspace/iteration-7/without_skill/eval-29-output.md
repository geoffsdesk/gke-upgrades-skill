Here's the exact configuration for your GKE maintenance exclusions and upgrade policies:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"
  
  # Disable automatic upgrades for minor versions
  node_config {
    # ... other node config
  }
  
  # Master maintenance policy
  maintenance_policy {
    # Recurring maintenance windows (optional - when you DO want maintenance)
    recurring_window {
      start_time = "2024-01-07T09:00:00Z"  # Sundays at 9 AM UTC
      end_time   = "2024-01-07T17:00:00Z"  # Sundays at 5 PM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    # June code freeze exclusion
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"  # Week before through week after
      end_time       = "2024-12-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }
  
  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "RAPID" or "STABLE"
  }
  
  # Control plane version pinning
  min_master_version = "1.28"  # Set to your desired version
}

# Node pool with controlled upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-nodes"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  
  # Disable auto-upgrade for minor versions
  management {
    auto_upgrade = false  # This prevents automatic minor version upgrades
    auto_repair  = true   # Keep auto-repair enabled for node health
  }
  
  # Control node version explicitly
  version = "1.28.3-gke.1286000"  # Pin to specific patch version
  
  upgrade_settings {
    strategy      = "SURGE"
    max_surge     = 1
    max_unavailable = 0
  }
}
```

## 2. gcloud CLI Configuration

```bash
#!/bin/bash

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
PROJECT_ID="your-project-id"

# Create the cluster with maintenance policy
gcloud container clusters create $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --release-channel=regular \
    --enable-autoupgrade \
    --maintenance-window-start="2024-01-07T09:00:00Z" \
    --maintenance-window-end="2024-01-07T17:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"

# Add June code freeze exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="all_upgrades"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope="all_upgrades"

# Disable auto-upgrade on node pools for manual control
gcloud container node-pools update default-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --no-enable-autoupgrade
```

## 3. YAML Configuration (for existing clusters)

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions
  namespace: kube-system
data:
  policy: |
    maintenancePolicy:
      window:
        recurringWindow:
          window:
            startTime: "2024-01-07T09:00:00Z"
            endTime: "2024-01-07T17:00:00Z"
          recurrence: "FREQ=WEEKLY;BYDAY=SU"
      maintenanceExclusions:
        june-code-freeze:
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-06-30T23:59:59Z"
          scope: ALL_UPGRADES
        black-friday-cyber-monday:
          startTime: "2024-11-20T00:00:00Z"
          endTime: "2024-12-05T23:59:59Z"
          scope: ALL_UPGRADES
```

## 4. Annual Update Script

```bash
#!/bin/bash
# update-yearly-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion="june-code-freeze-$CURRENT_YEAR" \
    --remove-maintenance-exclusion="black-friday-cyber-monday-$CURRENT_YEAR"

# Add new exclusions for next year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="all_upgrades"

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope="all_upgrades"
```

## 5. Manual Upgrade Process

```bash
#!/bin/bash
# manual-upgrade.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"

# Check available versions
gcloud container get-server-config --zone=$ZONE

# Upgrade control plane first
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version="1.29.0-gke.1381000"

# Wait for control plane upgrade to complete
echo "Waiting for control plane upgrade..."
sleep 300

# Upgrade node pools one by one
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool="default-pool"
```

## Key Points:

1. **Maintenance Exclusions**: Block ALL upgrades during June and Black Friday period
2. **Manual Control**: Disabled auto-upgrade on node pools for explicit approval
3. **Safe Windows**: Defined Sunday maintenance windows when upgrades ARE allowed
4. **Annual Management**: Script to update exclusions yearly
5. **Controlled Upgrades**: Manual upgrade process for when you're ready

## Important Notes:

- Update the dates annually in your infrastructure code
- Test upgrades in staging environments first
- Monitor GKE release notes for critical security patches that might override exclusions
- Consider using `SURGE` upgrade strategy to minimize downtime
- Keep auto-repair enabled even when auto-upgrade is disabled

This configuration gives you complete control over when upgrades happen while protecting your critical business periods.
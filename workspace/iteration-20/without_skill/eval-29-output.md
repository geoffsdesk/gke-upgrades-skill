I'll help you set up maintenance exclusions and policies for your GKE clusters to handle your specific requirements. Here's the exact configuration:

## 1. Maintenance Policy Configuration

### Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Maintenance policy configuration
  maintenance_policy {
    # Define maintenance window (adjust to your preferred time)
    daily_maintenance_window {
      start_time = "03:00"
    }

    # Maintenance exclusions
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-02T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Release channel configuration for controlled upgrades
  release_channel {
    channel = "STABLE"
  }

  # Node pool configuration
  node_pool {
    name       = "default-pool"
    node_count = 1

    # Auto-upgrade disabled for manual control
    management {
      auto_upgrade = false
      auto_repair  = true
    }

    node_config {
      machine_type = "e2-medium"
    }
  }
}

# Separate node pool with different maintenance settings if needed
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  management {
    auto_repair  = true
    auto_upgrade = false  # Disabled for manual control
  }

  node_config {
    preemptible  = false
    machine_type = "e2-standard-4"

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
    ]
  }
}
```

### gcloud Command Configuration

```bash
# Create cluster with maintenance policy
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start=2024-01-01T03:00:00Z \
    --maintenance-window-end=2024-01-01T07:00:00Z \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU" \
    --release-channel=stable \
    --no-enable-autoupgrade

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=quarterly-code-freeze-june \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-02T23:59:59Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES
```

## 2. YAML Configuration (for existing clusters)

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions-config
  namespace: kube-system
data:
  exclusions: |
    exclusions:
      - name: "quarterly-code-freeze-june"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        scope: "ALL_UPGRADES"
      - name: "black-friday-cyber-monday"
        startTime: "2024-11-20T00:00:00Z"
        endTime: "2024-12-02T23:59:59Z"
        scope: "ALL_UPGRADES"
```

## 3. Annual Maintenance Exclusion Script

Create a script to automatically update exclusions for recurring periods:

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to update June exclusion
update_june_exclusion() {
    local year=$1
    
    # Remove existing June exclusion if it exists
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --remove-maintenance-exclusion-name=quarterly-code-freeze-june-$year \
        --quiet || true
    
    # Add new June exclusion
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --add-maintenance-exclusion-name=quarterly-code-freeze-june-$year \
        --add-maintenance-exclusion-start=${year}-06-01T00:00:00Z \
        --add-maintenance-exclusion-end=${year}-06-30T23:59:59Z \
        --add-maintenance-exclusion-scope=ALL_UPGRADES
}

# Function to update Black Friday exclusion
update_blackfriday_exclusion() {
    local year=$1
    
    # Remove existing Black Friday exclusion if it exists
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --remove-maintenance-exclusion-name=black-friday-cyber-monday-$year \
        --quiet || true
    
    # Add new Black Friday exclusion
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --add-maintenance-exclusion-name=black-friday-cyber-monday-$year \
        --add-maintenance-exclusion-start=${year}-11-20T00:00:00Z \
        --add-maintenance-exclusion-end=${year}-12-02T23:59:59Z \
        --add-maintenance-exclusion-scope=ALL_UPGRADES
}

# Update exclusions for current and next year
update_june_exclusion $CURRENT_YEAR
update_blackfriday_exclusion $CURRENT_YEAR
update_june_exclusion $NEXT_YEAR
update_blackfriday_exclusion $NEXT_YEAR

echo "Maintenance exclusions updated successfully!"
```

## 4. Monitoring and Alerting Configuration

```yaml
# maintenance-alert-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEMaintenanceExclusionExpiring
      expr: |
        (
          time() > on() (
            maintenance_exclusion_end_time - 7*24*3600
          )
        ) and (
          time() < on() maintenance_exclusion_end_time
        )
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance exclusion expiring soon"
        description: "Maintenance exclusion will expire in less than 7 days"
```

## 5. Best Practices Configuration

### Node Pool Anti-Affinity for Zero-Downtime Updates

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: critical-app
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - critical-app
        topologyKey: kubernetes.io/hostname
```

### PodDisruptionBudget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: critical-app
```

## 6. Manual Upgrade Process

When you're ready to perform manual upgrades:

```bash
# Check available versions
gcloud container get-server-config --zone=us-central1-a

# Upgrade control plane
gcloud container clusters upgrade your-cluster-name \
    --master \
    --cluster-version=1.28.3-gke.1203001 \
    --zone=us-central1-a

# Upgrade node pools (one at a time)
gcloud container clusters upgrade your-cluster-name \
    --node-pool=default-pool \
    --cluster-version=1.28.3-gke.1203001 \
    --zone=us-central1-a
```

## Key Points:

1. **Auto-upgrade disabled**: Prevents minor version upgrades without approval
2. **Maintenance exclusions**: Block ALL_UPGRADES during critical periods
3. **Stable release channel**: Reduces frequency of available upgrades
4. **Annual script**: Automatically updates exclusion periods each year
5. **Monitoring**: Alerts when exclusions are about to expire

Make sure to run the annual update script before January each year to set up exclusions for the upcoming year!
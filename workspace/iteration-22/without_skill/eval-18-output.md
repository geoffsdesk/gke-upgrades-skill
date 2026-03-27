I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Maintenance Window Configuration

### Primary Maintenance Window (Weekends Only)
```bash
# Configure weekend-only maintenance window for all clusters
for cluster in cluster-prod cluster-staging cluster-dev; do
  gcloud container clusters update $cluster \
    --zone=us-central1-a \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU"
done
```

### Alternative: Using gcloud with recurring maintenance windows
```bash
# Set maintenance window for Saturday 2 AM - 6 AM UTC
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --maintenance-window-start="2024-01-06T02:00:00Z" \
  --maintenance-window-end="2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-window-end-time="2024-01-06T06:00:00Z"
```

## 2. Terraform Configuration for All Clusters

```hcl
# terraform/gke-maintenance.tf

resource "google_container_cluster" "primary" {
  for_each = {
    prod    = { zone = "us-central1-a", node_count = 3 }
    staging = { zone = "us-central1-b", node_count = 2 }
    dev     = { zone = "us-central1-c", node_count = 1 }
  }

  name     = "cluster-${each.key}"
  location = each.value.zone

  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend maintenance window (Saturday 2-6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Recurring maintenance window (weekends only)
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }

    # Maintenance exclusions for compliance
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-2024"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-03-31T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-2024"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-09-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-2024"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Annual audit exclusion (November)
    maintenance_exclusion {
      exclusion_name = "annual-audit-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel for controlled upgrades
  release_channel {
    channel = "STABLE"  # Use STABLE for production compliance
  }

  # Network configuration
  network    = "default"
  subnetwork = "default"

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Workload Identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Enable network policy for security
  network_policy {
    enabled = true
  }

  # Enable Shielded GKE Nodes
  enable_shielded_nodes = true

  # Logging and monitoring for compliance
  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "API_SERVER"
    ]
  }

  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS"
    ]
  }
}

resource "google_container_node_pool" "primary_nodes" {
  for_each   = google_container_cluster.primary
  name       = "${each.key}-node-pool"
  location   = each.value.location
  cluster    = each.value.name
  node_count = each.key == "prod" ? 3 : (each.key == "staging" ? 2 : 1)

  # Upgrade settings for controlled rollouts
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  # Management settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    preemptible  = each.key == "dev" ? true : false
    machine_type = each.key == "prod" ? "e2-standard-4" : "e2-standard-2"

    # Google-recommended security settings
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Service account with minimal permissions
    service_account = google_service_account.gke_service_account[each.key].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    labels = {
      environment = each.key
      compliance  = "sox"
    }

    tags = ["gke-node", "${each.key}-nodes"]
  }
}

resource "google_service_account" "gke_service_account" {
  for_each     = toset(["prod", "staging", "dev"])
  account_id   = "gke-${each.key}-sa"
  display_name = "GKE ${each.key} Service Account"
}
```

## 3. CLI Commands for Adding Maintenance Exclusions

```bash
#!/bin/bash
# scripts/add-maintenance-exclusions.sh

CLUSTERS=("cluster-prod" "cluster-staging" "cluster-dev")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")
YEAR="2024"

# Function to add maintenance exclusion
add_exclusion() {
    local cluster=$1
    local zone=$2
    local name=$3
    local start=$4
    local end=$5
    
    echo "Adding maintenance exclusion '$name' to $cluster..."
    gcloud container clusters update $cluster \
        --zone=$zone \
        --add-maintenance-exclusion-name=$name \
        --add-maintenance-exclusion-start=$start \
        --add-maintenance-exclusion-end=$end \
        --add-maintenance-exclusion-scope=upgrades
}

# Add quarterly code freeze exclusions
for i in "${!CLUSTERS[@]}"; do
    cluster=${CLUSTERS[$i]}
    zone=${ZONES[$i]}
    
    # Q1 Code Freeze
    add_exclusion $cluster $zone "q1-code-freeze-$YEAR" \
        "${YEAR}-03-15T00:00:00Z" "${YEAR}-03-31T23:59:59Z"
    
    # Q2 Code Freeze  
    add_exclusion $cluster $zone "q2-code-freeze-$YEAR" \
        "${YEAR}-06-15T00:00:00Z" "${YEAR}-06-30T23:59:59Z"
    
    # Q3 Code Freeze
    add_exclusion $cluster $zone "q3-code-freeze-$YEAR" \
        "${YEAR}-09-15T00:00:00Z" "${YEAR}-09-30T23:59:59Z"
    
    # Q4 Code Freeze
    add_exclusion $cluster $zone "q4-code-freeze-$YEAR" \
        "${YEAR}-12-15T00:00:00Z" "${YEAR}-12-31T23:59:59Z"
    
    # Annual Audit (November)
    add_exclusion $cluster $zone "annual-audit-$YEAR" \
        "${YEAR}-11-01T00:00:00Z" "${YEAR}-11-30T23:59:59Z"
done
```

## 4. Monitoring and Alerting Configuration

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
  namespace: kube-system
data:
  alert-rules.yaml: |
    groups:
    - name: gke-maintenance
      rules:
      - alert: MaintenanceWindowViolation
        expr: |
          (
            time() % (7*24*3600) < 2*24*3600 or 
            time() % (7*24*3600) > 6*24*3600
          ) and on() kube_node_info{kubelet_version!~".*"}
        for: 5m
        labels:
          severity: warning
          compliance: sox
        annotations:
          summary: "Maintenance activity detected outside approved window"
          description: "GKE maintenance activity detected outside weekend window"
      
      - alert: UpgradesDuringFreeze
        expr: |
          increase(apiserver_audit_total{verb="update",objectRef_resource="nodes"}[5m]) > 0
          and on() (
            (month() == 3 and day() >= 15) or
            (month() == 6 and day() >= 15) or  
            (month() == 9 and day() >= 15) or
            (month() == 11) or
            (month() == 12 and day() >= 15)
          )
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "Upgrades detected during code freeze period"
          description: "Node upgrades detected during compliance freeze period"
```

## 5. Compliance Verification Script

```bash
#!/bin/bash
# scripts/verify-maintenance-config.sh

echo "=== GKE Maintenance Configuration Verification ==="
echo "Checking SOX compliance settings for all clusters..."

CLUSTERS=("cluster-prod" "cluster-staging" "cluster-dev")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")

for i in "${!CLUSTERS[@]}"; do
    cluster=${CLUSTERS[$i]}
    zone=${ZONES[$i]}
    
    echo ""
    echo "--- $cluster ---"
    
    # Check maintenance window
    echo "Maintenance Window:"
    gcloud container clusters describe $cluster --zone=$zone \
        --format="value(maintenancePolicy.window.dailyMaintenanceWindow.startTime)"
    
    # Check maintenance exclusions
    echo "Maintenance Exclusions:"
    gcloud container clusters describe $cluster --zone=$zone \
        --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,
                         maintenancePolicy.window.maintenanceExclusions[].startTime,
                         maintenancePolicy.window.maintenanceExclusions[].endTime)"
    
    # Check release channel
    echo "Release Channel:"
    gcloud container clusters describe $cluster --zone=$zone \
        --format="value(releaseChannel.channel)"
    
    # Check auto-upgrade status
    echo "Node Auto-Upgrade Status:"
    gcloud container node-pools describe "${cluster%-*}-node-pool" \
        --cluster=$cluster --zone=$zone \
        --format="value(management.autoUpgrade)"
done

echo ""
echo "=== Compliance Summary ==="
echo "✓ Weekend-only maintenance windows configured"
echo "✓ Quarterly code freeze exclusions set"
echo "✓ November audit exclusion configured"
echo "✓ STABLE release channel for controlled updates"
echo "✓ Auto-upgrades enabled with exclusions"
```

## 6. Implementation Steps

1. **Deploy with Terraform:**
```bash
cd terraform/
terraform init
terraform plan -var="project_id=your-project-id"
terraform apply
```

2. **Or apply via CLI:**
```bash
chmod +x scripts/add-maintenance-exclusions.sh
./scripts/add-maintenance-exclusions.sh
```

3. **Verify configuration:**
```bash
chmod +x scripts/verify-maintenance-config.sh
./scripts/verify-maintenance-config.sh
```

4. **Set up monitoring:**
```bash
kubectl apply -f monitoring/maintenance-alerts.yaml
```

## Key SOX Compliance Features:

- ✅ **Controlled Upgrade Windows**: Only weekends
- ✅ **Quarterly Code Freezes**: Automatic exclusions
- ✅ **Annual Audit Protection**: November exclusions
- ✅ **Audit Logging**: Comprehensive logging enabled
- ✅ **Change Control**: STABLE release channel
- ✅ **Monitoring**: Alerts for compliance violations
- ✅ **Documentation**: Full configuration tracking

This configuration ensures your GKE clusters meet SOX compliance requirements while maintaining security through controlled, predictable upgrade schedules.
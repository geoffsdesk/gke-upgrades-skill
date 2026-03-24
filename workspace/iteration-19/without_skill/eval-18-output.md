I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive setup:

## 1. Cluster Configuration with Maintenance Windows

```yaml
# cluster-maintenance-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
  namespace: kube-system
data:
  schedule: "Weekend maintenance windows with quarterly freezes"
---
# Apply to each cluster
```

```bash
# Configure maintenance window for each cluster
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"  # Adjust to your region

for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance window for $CLUSTER..."
  
  # Set weekend maintenance window (Saturday 2 AM UTC, 4-hour window)
  gcloud container clusters update $CLUSTER \
    --region=$REGION \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
done
```

## 2. Terraform Configuration for Maintenance Windows

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  count    = 3
  name     = "prod-cluster-${count.index + 1}"
  location = var.region

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"  # 2 AM
    }
    
    # Alternative: Use recurring window for weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # Saturday
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # or "STABLE" for more conservative updates
  }

  # Workload Identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy for compliance
  network_policy {
    enabled = true
  }

  # Private cluster configuration
  private_cluster_config {
    enable_private_endpoint = true
    enable_private_nodes    = true
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Binary authorization for compliance
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  tags = ["sox-compliant", "production"]
}

# Maintenance exclusions for quarterly freezes and audit
resource "google_container_cluster" "primary" {
  # ... other configuration ...

  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Q1 Code Freeze (March)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-2024"
      start_time     = "2024-03-01T00:00:00Z"
      end_time       = "2024-03-31T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    # Q2 Code Freeze (June)
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    # Q3 Code Freeze (September)
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-2024"
      start_time     = "2024-09-01T00:00:00Z"
      end_time       = "2024-09-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    # Q4 Code Freeze + Annual Audit (November-December)
    maintenance_exclusion {
      exclusion_name = "q4-freeze-annual-audit-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }
  }
}
```

## 3. Node Pool Configuration with Auto-Upgrade Control

```hcl
# node-pools.tf
resource "google_container_node_pool" "primary_nodes" {
  count   = 3
  name    = "prod-nodes-${count.index + 1}"
  cluster = google_container_cluster.primary[count.index].name
  location = var.region

  # Node configuration
  node_config {
    preemptible  = false
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-ssd"

    # Security configurations
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Compliance labels
    labels = {
      environment = "production"
      compliance  = "sox"
      team        = "platform"
    }

    tags = ["gke-node", "production"]
  }

  # Auto-scaling
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }

  # Management and upgrade policy
  management {
    auto_repair  = true
    auto_upgrade = true  # Will respect maintenance windows
  }

  upgrade_settings {
    strategy = "SURGE"
    max_surge = 1
    max_unavailable = 0  # Zero downtime for production
  }
}
```

## 4. Monitoring and Compliance Script

```bash
#!/bin/bash
# maintenance-compliance-check.sh

set -e

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"
LOGFILE="/var/log/gke-maintenance-$(date +%Y%m%d).log"

echo "=== GKE Maintenance Compliance Check - $(date) ===" | tee -a $LOGFILE

for CLUSTER in "${CLUSTERS[@]}"; do
    echo "Checking cluster: $CLUSTER" | tee -a $LOGFILE
    
    # Check maintenance window configuration
    echo "Maintenance Window Status:" | tee -a $LOGFILE
    gcloud container clusters describe $CLUSTER \
        --region=$REGION \
        --format="value(maintenancePolicy.window)" | tee -a $LOGFILE
    
    # Check for any pending upgrades
    echo "Upgrade Status:" | tee -a $LOGFILE
    gcloud container clusters describe $CLUSTER \
        --region=$REGION \
        --format="value(currentMasterVersion,currentNodeVersion)" | tee -a $LOGFILE
    
    # Check node pool auto-upgrade status
    echo "Node Pool Auto-upgrade Status:" | tee -a $LOGFILE
    gcloud container node-pools list \
        --cluster=$CLUSTER \
        --region=$REGION \
        --format="table(name,management.autoUpgrade)" | tee -a $LOGFILE
    
    echo "---" | tee -a $LOGFILE
done

# Send compliance report
echo "Compliance check completed. Log available at: $LOGFILE"
```

## 5. Automated Maintenance Exclusion Management

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

YEAR=$(date +%Y)
NEXT_YEAR=$((YEAR + 1))
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"

# Function to add maintenance exclusion
add_exclusion() {
    local cluster=$1
    local name=$2
    local start=$3
    local end=$4
    
    echo "Adding exclusion '$name' to cluster $cluster"
    gcloud container clusters update $cluster \
        --region=$REGION \
        --add-maintenance-exclusion-end=$end \
        --add-maintenance-exclusion-name=$name \
        --add-maintenance-exclusion-start=$start \
        --add-maintenance-exclusion-scope=UPGRADES
}

# Add exclusions for next year
for CLUSTER in "${CLUSTERS[@]}"; do
    echo "Updating maintenance exclusions for $CLUSTER..."
    
    # Q1 Code Freeze
    add_exclusion $CLUSTER "q1-code-freeze-$NEXT_YEAR" \
        "${NEXT_YEAR}-03-01T00:00:00Z" \
        "${NEXT_YEAR}-03-31T23:59:59Z"
    
    # Q2 Code Freeze
    add_exclusion $CLUSTER "q2-code-freeze-$NEXT_YEAR" \
        "${NEXT_YEAR}-06-01T00:00:00Z" \
        "${NEXT_YEAR}-06-30T23:59:59Z"
    
    # Q3 Code Freeze
    add_exclusion $CLUSTER "q3-code-freeze-$NEXT_YEAR" \
        "${NEXT_YEAR}-09-01T00:00:00Z" \
        "${NEXT_YEAR}-09-30T23:59:59Z"
    
    # Q4 + Annual Audit
    add_exclusion $CLUSTER "q4-freeze-annual-audit-$NEXT_YEAR" \
        "${NEXT_YEAR}-11-01T00:00:00Z" \
        "${NEXT_YEAR}-12-31T23:59:59Z"
done
```

## 6. Cloud Monitoring Alerts

```yaml
# maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEMaintenanceWindowViolation
      expr: up{job="kubernetes-nodes"} == 0
      for: 5m
      during:
        - start: "Monday 00:00"
          end: "Friday 23:59"
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "GKE maintenance detected outside approved window"
        description: "Cluster maintenance or upgrade activity detected during business hours"

    - alert: GKEVersionDrift
      expr: |
        (
          kubernetes_build_info{job="kubernetes-apiservers"} 
          != on() group_left() 
          kubernetes_build_info{job="kubernetes-apiservers"} offset 1h
        )
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "GKE cluster version changed"
        description: "Kubernetes version change detected - verify compliance approval"
```

## 7. Deployment Script

```bash
#!/bin/bash
# deploy-maintenance-config.sh

set -e

echo "Deploying GKE maintenance configuration for SOX compliance..."

# Apply Terraform configuration
echo "Applying Terraform configuration..."
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Set up monitoring
echo "Setting up monitoring and alerting..."
kubectl apply -f maintenance-alerts.yaml

# Create compliance check cron job
echo "Setting up compliance monitoring..."
cat << EOF | kubectl apply -f -
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-compliance-check
  namespace: kube-system
spec:
  schedule: "0 8 * * MON"  # Every Monday at 8 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: compliance-check
            image: google/cloud-sdk:alpine
            command:
            - /bin/sh
            - -c
            - |
              gcloud auth activate-service-account --key-file=/var/secrets/google/key.json
              /scripts/maintenance-compliance-check.sh
            volumeMounts:
            - name: service-account
              mountPath: /var/secrets/google
            - name: scripts
              mountPath: /scripts
          volumes:
          - name: service-account
            secret:
              secretName: gcp-service-account
          - name: scripts
            configMap:
              name: compliance-scripts
              defaultMode: 0755
          restartPolicy: OnFailure
EOF

echo "SOX-compliant GKE maintenance configuration deployed successfully!"
echo ""
echo "Summary:"
echo "- Maintenance windows: Saturdays 2-6 AM UTC"
echo "- Quarterly code freezes: March, June, September"
echo "- Annual audit exclusion: November-December"
echo "- Auto-upgrades enabled within maintenance windows only"
echo "- Compliance monitoring and alerting configured"
```

This configuration provides:

1. **Weekend-only maintenance windows** (Saturday 2-6 AM)
2. **Quarterly code freeze exclusions** (March, June, September)
3. **Extended exclusion for November audit period**
4. **Automated compliance monitoring**
5. **Zero-downtime upgrade strategy**
6. **SOX compliance logging and alerting**

The setup ensures that all cluster upgrades happen only during approved maintenance windows while maintaining detailed audit logs for compliance reporting.
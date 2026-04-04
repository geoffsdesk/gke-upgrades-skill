You're in a common but fixable situation! Here's a structured approach to get your GKE fleet healthy using Google's built-in tools:

## 1. Assessment & Discovery Tools

### GKE Usage Metering
```bash
# Enable usage metering for cost and resource visibility
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --enable-network-policy \
  --resource-usage-bigquery-dataset DATASET_NAME
```

### Binary Authorization & Policy Controller
```bash
# Check security posture across clusters
gcloud container binauthz policy import policy.yaml
```

### Asset Inventory
```bash
# Get comprehensive cluster inventory
gcloud asset search-all-resources \
  --asset-types='container.googleapis.com/Cluster' \
  --format='table(name,location,additionalAttributes.currentMasterVersion)'
```

## 2. Fleet Management Setup

### Enable GKE Enterprise (formerly Anthos)
```bash
# Register clusters to a fleet for centralized management
gcloud container fleet memberships register CLUSTER_NAME \
  --gke-cluster=LOCATION/CLUSTER_NAME \
  --enable-workload-identity
```

### Config Management for GitOps
```yaml
# config-management.yaml
apiVersion: configmanagement.gke.io/v1
kind: ConfigManagement
metadata:
  name: config-management
spec:
  git:
    syncRepo: https://github.com/your-org/k8s-configs
    syncBranch: main
    secretType: none
  policyController:
    enabled: true
    templateLibraryInstalled: true
```

## 3. Version & Channel Standardization

### Assessment Script
```bash
#!/bin/bash
# cluster-audit.sh
echo "Cluster Name,Location,Version,Channel,Node Pools"

gcloud container clusters list --format="csv[no-heading](name,location,currentMasterVersion,releaseChannel.channel,nodePools[].name)" | \
while IFS=',' read -r name location version channel nodepools; do
  echo "$name,$location,$version,$channel,$nodepools"
done
```

### Standardize on Release Channels
```bash
# Move clusters to Regular channel (recommended for most workloads)
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --release-channel=regular

# For production: consider Stable channel
gcloud container clusters update PROD_CLUSTER \
  --zone=ZONE \
  --release-channel=stable
```

## 4. Automated Health Monitoring

### Policy Controller for Governance
```yaml
# Example: Require resource limits
apiVersion: templates.gatekeeper.sh/v1beta1
kind: K8sRequiredResources
metadata:
  name: must-have-limits
spec:
  match:
    kinds:
    - apiGroups: [""]
      kinds: ["Pod"]
  parameters:
    limits: ["memory", "cpu"]
```

### Set up Monitoring Dashboard
```bash
# Enable monitoring and logging
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --enable-cloud-logging \
  --enable-cloud-monitoring \
  --logging=SYSTEM,WORKLOAD \
  --monitoring=SYSTEM
```

## 5. Migration Strategy

### Phased Approach
```bash
# 1. Non-production clusters first
DEV_CLUSTERS=$(gcloud container clusters list --filter="name~'dev|test|staging'" --format="value(name,zone)")

# 2. Update maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --maintenance-window-start="2023-01-01T09:00:00Z" \
  --maintenance-window-end="2023-01-01T17:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

### Cluster Upgrade Automation
```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region

  release_channel {
    channel = "REGULAR"
  }

  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T09:00:00Z"
      end_time   = "2023-01-01T17:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  # Enable auto-repair and auto-upgrade
  node_config {
    machine_type = "e2-medium"
  }

  node_pool {
    management {
      auto_repair  = true
      auto_upgrade = true
    }
  }
}
```

## 6. Self-Service Assessment Tools

### GKE Security Posture Dashboard
Access via Google Cloud Console → GKE → Security

### Cost Optimization Recommendations
```bash
# Get rightsizing recommendations
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --recommender=google.container.DiagnosisRecommender \
  --location=LOCATION
```

### Fleet Observability
Set up centralized logging and monitoring:
```bash
# Enable fleet observability
gcloud container fleet cloudrun enable
gcloud container fleet mesh enable
```

## 7. Quick Wins Checklist

- [ ] Enable Binary Authorization
- [ ] Set up maintenance windows
- [ ] Move to release channels
- [ ] Enable Workload Identity
- [ ] Configure network policies
- [ ] Set up Config Sync
- [ ] Enable security posture monitoring
- [ ] Configure backup for stateful workloads

## 8. Ongoing Management

### Weekly Health Check Script
```bash
#!/bin/bash
# weekly-health-check.sh
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,status,releaseChannel.channel)" \
  --filter="status=RUNNING"

# Check for available updates
gcloud container get-server-config \
  --format="yaml(channels)" \
  --zone=us-central1-a
```

Start with the assessment tools, prioritize security and compliance issues, then systematically move through version standardization. The fleet management features will give you the centralized control you need to prevent this situation from recurring.
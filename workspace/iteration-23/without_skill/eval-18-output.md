I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive solution:

## 1. Maintenance Window Configuration

First, let's set up weekend-only maintenance windows for all three clusters:

```yaml
# maintenance-window-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
data:
  # Weekend maintenance window: Saturday 2 AM - 6 AM UTC
  start-time: "2023-01-07T02:00:00Z"  # Saturday
  end-time: "2023-01-07T06:00:00Z"
  recurrence: "FREQ=WEEKLY;BYDAY=SA"
```

## 2. Terraform Configuration

```hcl
# maintenance-windows.tf
variable "cluster_names" {
  description = "List of GKE cluster names"
  type        = list(string)
  default     = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
}

# Maintenance policy for each cluster
resource "google_container_cluster" "clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  project  = var.project_id
  location = var.region

  # Maintenance policy configuration
  maintenance_policy {
    # Weekend maintenance window (Saturday 2-6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Maintenance exclusions for compliance
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-2024"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-04-01T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-07-01T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-2024"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-10-01T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "november-audit-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-2024"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2025-01-01T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring maintenance window (weekends only)
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # Saturday
      end_time   = "2024-01-06T06:00:00Z"  # Saturday
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  # Enable auto-upgrade with maintenance policy constraints
  cluster_autoscaling {
    enabled = true
  }

  # Node pool configuration with auto-upgrade
  node_pool {
    name = "default-pool"
    
    management {
      auto_repair  = true
      auto_upgrade = true
    }
    
    upgrade_settings {
      max_surge       = 1
      max_unavailable = 0
      strategy        = "SURGE"
    }
  }
}
```

## 3. Advanced Maintenance Policy with gcloud

For more granular control, use gcloud commands:

```bash
#!/bin/bash
# maintenance-setup.sh

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
PROJECT_ID="your-project-id"
REGION="us-central1"

for cluster in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance policy for $cluster..."
  
  # Set recurring weekend maintenance window
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
  
  # Add quarterly code freeze exclusions
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="q1-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-04-01T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
    
  # Add November audit exclusion
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="november-audit-2024" \
    --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
done
```

## 4. SOX Compliance Monitoring Script

```python
#!/usr/bin/env python3
# maintenance-compliance-monitor.py

import json
import subprocess
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MaintenanceComplianceMonitor:
    def __init__(self, project_id, clusters):
        self.project_id = project_id
        self.clusters = clusters
    
    def check_maintenance_policy(self, cluster_name, region):
        """Check current maintenance policy for a cluster"""
        try:
            cmd = [
                'gcloud', 'container', 'clusters', 'describe', cluster_name,
                '--project', self.project_id,
                '--region', region,
                '--format', 'json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            cluster_info = json.loads(result.stdout)
            
            maintenance_policy = cluster_info.get('maintenancePolicy', {})
            return maintenance_policy
            
        except Exception as e:
            logger.error(f"Error checking maintenance policy for {cluster_name}: {e}")
            return None
    
    def validate_exclusions(self, maintenance_policy):
        """Validate that required exclusions are in place"""
        exclusions = maintenance_policy.get('window', {}).get('maintenanceExclusions', {})
        
        required_exclusions = [
            'q1-code-freeze-2024',
            'q2-code-freeze-2024', 
            'q3-code-freeze-2024',
            'q4-code-freeze-2024',
            'november-audit-2024'
        ]
        
        missing_exclusions = []
        for exclusion in required_exclusions:
            if exclusion not in exclusions:
                missing_exclusions.append(exclusion)
        
        return missing_exclusions
    
    def generate_compliance_report(self):
        """Generate compliance report for all clusters"""
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'clusters': {}
        }
        
        for cluster in self.clusters:
            cluster_name = cluster['name']
            cluster_region = cluster['region']
            
            maintenance_policy = self.check_maintenance_policy(cluster_name, cluster_region)
            
            if maintenance_policy:
                missing_exclusions = self.validate_exclusions(maintenance_policy)
                
                report['clusters'][cluster_name] = {
                    'compliant': len(missing_exclusions) == 0,
                    'missing_exclusions': missing_exclusions,
                    'maintenance_window': maintenance_policy.get('window', {}).get('recurringWindow', {}),
                    'last_checked': datetime.now(timezone.utc).isoformat()
                }
            else:
                report['clusters'][cluster_name] = {
                    'compliant': False,
                    'error': 'Could not retrieve maintenance policy'
                }
        
        return report

# Usage
if __name__ == "__main__":
    clusters = [
        {'name': 'prod-cluster-1', 'region': 'us-central1'},
        {'name': 'prod-cluster-2', 'region': 'us-central1'},
        {'name': 'prod-cluster-3', 'region': 'us-central1'}
    ]
    
    monitor = MaintenanceComplianceMonitor('your-project-id', clusters)
    report = monitor.generate_compliance_report()
    
    print(json.dumps(report, indent=2))
```

## 5. Automated Exclusion Management

```yaml
# exclusion-scheduler.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-exclusion-manager
  namespace: kube-system
spec:
  schedule: "0 0 1 */3 *"  # Run quarterly
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: maintenance-manager
          containers:
          - name: exclusion-manager
            image: google/cloud-sdk:alpine
            command:
            - /bin/bash
            - -c
            - |
              # Add next quarter's exclusion
              NEXT_QUARTER_START=$(date -d "+3 months" +%Y-%m-15T00:00:00Z)
              NEXT_QUARTER_END=$(date -d "+4 months" +%Y-%m-01T23:59:59Z)
              EXCLUSION_NAME="code-freeze-$(date -d "+3 months" +%Y-q%q)"
              
              for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3; do
                gcloud container clusters update $cluster \
                  --region=us-central1 \
                  --add-maintenance-exclusion-name="$EXCLUSION_NAME" \
                  --add-maintenance-exclusion-start="$NEXT_QUARTER_START" \
                  --add-maintenance-exclusion-end="$NEXT_QUARTER_END" \
                  --add-maintenance-exclusion-scope="ALL_UPGRADES"
              done
            env:
            - name: GOOGLE_APPLICATION_CREDENTIALS
              value: /var/secrets/google/key.json
            volumeMounts:
            - name: google-cloud-key
              mountPath: /var/secrets/google
          volumes:
          - name: google-cloud-key
            secret:
              secretName: gcp-service-account
          restartPolicy: OnFailure
```

## 6. Service Account and RBAC

```yaml
# rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: maintenance-manager
  namespace: kube-system
  annotations:
    iam.gke.io/gcp-service-account: maintenance-manager@your-project-id.iam.gserviceaccount.com
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: maintenance-manager
rules:
- apiGroups: [""]
  resources: ["nodes", "pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: maintenance-manager
subjects:
- kind: ServiceAccount
  name: maintenance-manager
  namespace: kube-system
roleRef:
  kind: ClusterRole
  name: maintenance-manager
  apiGroup: rbac.authorization.k8s.io
```

## 7. Deployment and Verification

```bash
# deploy.sh
#!/bin/bash

# Apply Terraform configuration
terraform init
terraform plan -var="project_id=your-project-id" -var="region=us-central1"
terraform apply -auto-approve

# Deploy monitoring components
kubectl apply -f rbac.yaml
kubectl apply -f exclusion-scheduler.yaml

# Run compliance check
python3 maintenance-compliance-monitor.py

# Verify maintenance windows
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3; do
  echo "=== Maintenance Policy for $cluster ==="
  gcloud container clusters describe $cluster \
    --region=us-central1 \
    --format="yaml(maintenancePolicy)"
  echo
done
```

This configuration provides:

- **Weekend-only upgrades** (Saturday 2-6 AM UTC)
- **Quarterly code freeze exclusions** (mid-March to April 1, etc.)
- **November audit exclusion** (entire month)
- **Automated compliance monitoring**
- **SOX-compliant change tracking**

The setup ensures all maintenance activities are blocked during your sensitive periods while allowing necessary updates during approved maintenance windows.
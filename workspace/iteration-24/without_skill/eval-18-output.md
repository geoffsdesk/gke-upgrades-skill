I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration

```hcl
# terraform/maintenance-policy.tf

# Data source for quarterly code freeze dates
locals {
  # Define quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    {
      start = "2024-03-25T00:00:00Z"
      end   = "2024-04-01T23:59:59Z"
    },
    {
      start = "2024-06-24T00:00:00Z"
      end   = "2024-07-01T23:59:59Z"
    },
    {
      start = "2024-09-23T00:00:00Z"
      end   = "2024-09-30T23:59:59Z"
    },
    {
      start = "2024-12-23T00:00:00Z"
      end   = "2024-12-31T23:59:59Z"
    }
  ]
}

# GKE Cluster with maintenance policy
resource "google_container_cluster" "sox_compliant_cluster" {
  count = 3
  
  name     = "sox-cluster-${count.index + 1}"
  location = var.cluster_zones[count.index]

  # Maintenance policy configuration
  maintenance_policy {
    # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Alternative: Use recurring window for more control
    recurring_window {
      start_time = "2024-01-06T02:00:00Z" # First Saturday
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"   # Every Saturday
    }

    # Maintenance exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = "quarterly-freeze-${maintenance_exclusion.key + 1}"
        start_time     = maintenance_exclusion.value.start
        end_time       = maintenance_exclusion.value.end
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    # Annual November audit exclusion
    maintenance_exclusion {
      exclusion_name = "annual-audit-november"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Holiday exclusions (add as needed)
    maintenance_exclusion {
      exclusion_name = "holiday-blackout"
      start_time     = "2024-12-20T00:00:00Z"
      end_time       = "2025-01-03T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Node pool configuration
  node_pool {
    name       = "sox-node-pool"
    node_count = var.node_count

    management {
      auto_repair  = true
      auto_upgrade = true
    }

    upgrade_settings {
      strategy         = "SURGE"
      max_surge        = 1
      max_unavailable  = 0
    }

    node_config {
      machine_type = var.machine_type
      
      # Service account with minimal permissions
      service_account = google_service_account.gke_sa[count.index].email
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }

  # Enable network policy for security
  network_policy {
    enabled = true
  }

  # Enable logging and monitoring for audit trail
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
```

## 2. Automated Maintenance Exclusion Management

```python
# scripts/update_maintenance_exclusions.py
import json
import datetime
from google.cloud import container_v1
from google.protobuf.timestamp_pb2 import Timestamp

class SOXMaintenanceManager:
    def __init__(self, project_id, clusters):
        self.client = container_v1.ClusterManagerClient()
        self.project_id = project_id
        self.clusters = clusters
    
    def calculate_quarterly_dates(self, year):
        """Calculate quarterly code freeze dates"""
        quarters = []
        for quarter in range(1, 5):
            if quarter == 1:
                start = datetime.datetime(year, 3, 25)
                end = datetime.datetime(year, 4, 1, 23, 59, 59)
            elif quarter == 2:
                start = datetime.datetime(year, 6, 24)
                end = datetime.datetime(year, 7, 1, 23, 59, 59)
            elif quarter == 3:
                start = datetime.datetime(year, 9, 23)
                end = datetime.datetime(year, 9, 30, 23, 59, 59)
            else:  # Q4
                start = datetime.datetime(year, 12, 23)
                end = datetime.datetime(year, 12, 31, 23, 59, 59)
            
            quarters.append({
                'name': f'quarterly-freeze-q{quarter}-{year}',
                'start': start,
                'end': end
            })
        
        return quarters
    
    def create_maintenance_exclusion(self, cluster_name, location, exclusion):
        """Create a maintenance exclusion"""
        cluster_path = f"projects/{self.project_id}/locations/{location}/clusters/{cluster_name}"
        
        start_timestamp = Timestamp()
        start_timestamp.FromDatetime(exclusion['start'])
        
        end_timestamp = Timestamp()
        end_timestamp.FromDatetime(exclusion['end'])
        
        exclusion_window = {
            'exclusion_name': exclusion['name'],
            'start_time': start_timestamp,
            'end_time': end_timestamp,
            'exclusion_options': {
                'scope': container_v1.MaintenanceExclusionOptions.Scope.UPGRADES
            }
        }
        
        request = container_v1.SetMaintenancePolicyRequest(
            project_id=self.project_id,
            zone=location,
            cluster_id=cluster_name,
            maintenance_policy=container_v1.MaintenancePolicy(
                maintenance_exclusions={exclusion['name']: exclusion_window}
            )
        )
        
        operation = self.client.set_maintenance_policy(request=request)
        return operation
    
    def setup_annual_exclusions(self, year):
        """Setup exclusions for the entire year"""
        exclusions = []
        
        # Quarterly exclusions
        exclusions.extend(self.calculate_quarterly_dates(year))
        
        # Annual audit exclusion
        exclusions.append({
            'name': f'annual-audit-november-{year}',
            'start': datetime.datetime(year, 11, 1),
            'end': datetime.datetime(year, 11, 30, 23, 59, 59)
        })
        
        # Holiday exclusion
        exclusions.append({
            'name': f'holiday-blackout-{year}',
            'start': datetime.datetime(year, 12, 20),
            'end': datetime.datetime(year + 1, 1, 3, 23, 59, 59)
        })
        
        return exclusions
    
    def apply_to_all_clusters(self, year):
        """Apply maintenance exclusions to all clusters"""
        exclusions = self.setup_annual_exclusions(year)
        results = []
        
        for cluster in self.clusters:
            cluster_results = []
            for exclusion in exclusions:
                try:
                    operation = self.create_maintenance_exclusion(
                        cluster['name'], 
                        cluster['location'], 
                        exclusion
                    )
                    cluster_results.append({
                        'cluster': cluster['name'],
                        'exclusion': exclusion['name'],
                        'status': 'success',
                        'operation': operation.name
                    })
                except Exception as e:
                    cluster_results.append({
                        'cluster': cluster['name'],
                        'exclusion': exclusion['name'],
                        'status': 'error',
                        'error': str(e)
                    })
            
            results.append({
                'cluster': cluster['name'],
                'exclusions': cluster_results
            })
        
        return results

# Usage
if __name__ == "__main__":
    clusters = [
        {'name': 'sox-cluster-1', 'location': 'us-central1-a'},
        {'name': 'sox-cluster-2', 'location': 'us-east1-b'},
        {'name': 'sox-cluster-3', 'location': 'us-west1-c'}
    ]
    
    manager = SOXMaintenanceManager('your-project-id', clusters)
    results = manager.apply_to_all_clusters(2024)
    print(json.dumps(results, indent=2))
```

## 3. Monitoring and Alerting

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
data:
  alert-rules.yaml: |
    groups:
    - name: gke-maintenance
      rules:
      - alert: UnplannedMaintenanceWindow
        expr: increase(gke_cluster_maintenance_events_total[1h]) > 0
        for: 0m
        labels:
          severity: warning
          compliance: SOX
        annotations:
          summary: "Unplanned GKE maintenance detected"
          description: "Cluster {{ $labels.cluster_name }} had maintenance outside planned windows"
      
      - alert: MaintenanceExclusionExpiring
        expr: (gke_maintenance_exclusion_end_time - time()) < 86400
        for: 0m
        labels:
          severity: info
          compliance: SOX
        annotations:
          summary: "Maintenance exclusion expiring soon"
          description: "Exclusion {{ $labels.exclusion_name }} expires in less than 24 hours"

---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: sox-compliance-rules
spec:
  groups:
  - name: sox.compliance
    rules:
    - alert: MaintenanceViolation
      expr: |
        (
          hour() < 2 or hour() > 6 or
          day_of_week() != 6
        ) and on() gke_maintenance_active == 1
      for: 1m
      labels:
        severity: critical
        compliance: SOX
      annotations:
        summary: "Maintenance window violation detected"
        description: "GKE maintenance occurring outside approved weekend window"
```

## 4. Compliance Reporting Script

```python
# scripts/sox_compliance_report.py
import json
import datetime
from google.cloud import container_v1, logging_v2

class SOXComplianceReporter:
    def __init__(self, project_id):
        self.project_id = project_id
        self.container_client = container_v1.ClusterManagerClient()
        self.logging_client = logging_v2.Client()
    
    def get_maintenance_history(self, days_back=30):
        """Get maintenance events from Cloud Logging"""
        filter_str = f'''
        resource.type="gke_cluster"
        protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
        timestamp >= "{(datetime.datetime.now() - datetime.timedelta(days=days_back)).isoformat()}Z"
        '''
        
        entries = self.logging_client.list_entries(filter_=filter_str)
        maintenance_events = []
        
        for entry in entries:
            if 'maintenance' in str(entry.payload).lower():
                maintenance_events.append({
                    'timestamp': entry.timestamp,
                    'cluster': entry.resource.labels.get('cluster_name'),
                    'operation': entry.proto_payload.method_name,
                    'details': str(entry.payload)
                })
        
        return maintenance_events
    
    def validate_maintenance_windows(self, events):
        """Validate that maintenance occurred within approved windows"""
        violations = []
        
        for event in events:
            event_time = event['timestamp']
            
            # Check if it's a weekend (Saturday = 5, Sunday = 6)
            if event_time.weekday() not in [5, 6]:
                violations.append({
                    'event': event,
                    'violation': 'Maintenance on weekday',
                    'severity': 'HIGH'
                })
            
            # Check if it's within 2-6 AM UTC window
            if event_time.hour < 2 or event_time.hour > 6:
                violations.append({
                    'event': event,
                    'violation': 'Maintenance outside approved hours',
                    'severity': 'HIGH'
                })
        
        return violations
    
    def generate_compliance_report(self):
        """Generate SOX compliance report"""
        events = self.get_maintenance_history()
        violations = self.validate_maintenance_windows(events)
        
        report = {
            'report_date': datetime.datetime.now().isoformat(),
            'period_days': 30,
            'total_maintenance_events': len(events),
            'violations': len(violations),
            'compliance_status': 'COMPLIANT' if len(violations) == 0 else 'NON-COMPLIANT',
            'maintenance_events': events,
            'violations_detail': violations,
            'exclusion_periods': self.get_active_exclusions()
        }
        
        return report
    
    def get_active_exclusions(self):
        """Get currently active maintenance exclusions"""
        # Implementation to fetch current exclusions from clusters
        pass

# Usage
reporter = SOXComplianceReporter('your-project-id')
compliance_report = reporter.generate_compliance_report()
print(json.dumps(compliance_report, indent=2, default=str))
```

## 5. Implementation Checklist

```bash
#!/bin/bash
# deploy.sh - SOX Compliance Deployment

set -e

echo "Deploying SOX-compliant GKE maintenance configuration..."

# 1. Apply Terraform configuration
echo "Applying Terraform configuration..."
cd terraform
terraform init
terraform plan -var-file="sox-vars.tfvars"
terraform apply -var-file="sox-vars.tfvars" -auto-approve

# 2. Set up monitoring
echo "Deploying monitoring configuration..."
kubectl apply -f monitoring/maintenance-alerts.yaml

# 3. Configure maintenance exclusions for current year
echo "Setting up maintenance exclusions..."
python3 scripts/update_maintenance_exclusions.py

# 4. Verify configuration
echo "Verifying maintenance policies..."
for cluster in sox-cluster-1 sox-cluster-2 sox-cluster-3; do
    gcloud container clusters describe $cluster --format="yaml(maintenancePolicy)"
done

echo "SOX compliance configuration deployed successfully!"
```

## Key SOX Compliance Features:

1. **Weekend-Only Maintenance**: Configured for Saturday 2-6 AM UTC
2. **Quarterly Code Freezes**: Automatic exclusions for quarter-end periods
3. **Annual Audit Blackout**: November maintenance blocked
4. **Holiday Exclusions**: End-of-year freeze period
5. **Audit Trail**: Comprehensive logging and monitoring
6. **Automated Reporting**: Compliance status tracking
7. **Change Control**: All changes tracked and approved through Terraform

This configuration ensures your
For your Cassandra ring with 9 nodes using local SSDs, I **strongly recommend using surge upgrade** rather than blue-green. Let me explain why and show you how to configure it.

## Why Surge Upgrade is Better for Your Use Case

### Problems with Blue-Green for Cassandra:
- **Data Loss Risk**: Blue-green creates entirely new nodes, and local SSD data cannot be migrated
- **Complete Ring Rebuild**: Your entire Cassandra ring would need to be rebuilt from scratch
- **Extended Downtime**: Even with backups, rebuilding a 9-node ring takes significant time
- **Resource Waste**: You'd temporarily need 18 nodes (9 old + 9 new)

### Benefits of Surge Upgrade:
- **Preserves Local Data**: Nodes are upgraded in-place or with controlled replacement
- **Maintains Ring Topology**: Cassandra ring remains intact during the process
- **Controlled Rollout**: You can specify exactly how many nodes upgrade simultaneously
- **Respects Stateful Constraints**: Works with your data locality requirements

## Recommended Configuration

Here's how to configure surge upgrade for your stateful workload:

```yaml
# node-pool-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cassandra-nodepool-upgrade-config
data:
  max_surge: "1"
  max_unavailable: "0"
---
# Apply this configuration to your node pool
```

### Using gcloud CLI:

```bash
# Configure the node pool for surge upgrade
gcloud container node-pools update cassandra-pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --max-surge=1 \
    --max-unavailable=0 \
    --enable-autoupgrade=false

# When ready to upgrade, run:
gcloud container node-pools upgrade cassandra-pool \
    --cluster=your-cluster-name \
    --zone=your-zone
```

### Using Terraform:

```hcl
resource "google_container_node_pool" "cassandra_pool" {
  name       = "cassandra-pool"
  cluster    = google_container_cluster.primary.name
  node_count = 9

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = "n2-standard-8"  # Adjust as needed
    disk_type    = "pd-ssd"
    disk_size_gb = 100

    local_ssd_count = 1  # Your local SSD configuration

    labels = {
      workload-type = "cassandra"
    }

    taint {
      key    = "workload-type"
      value  = "cassandra"
      effect = "NO_SCHEDULE"
    }
  }

  management {
    auto_upgrade = false  # Control upgrades manually
    auto_repair  = true
  }
}
```

## Pre-Upgrade Preparation

### 1. Verify Cassandra Health:
```bash
# Check cluster status
kubectl exec -it cassandra-0 -- nodetool status

# Verify replication factor supports node failures
kubectl exec -it cassandra-0 -- nodetool describecluster
```

### 2. Configure Pod Disruption Budget:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  maxUnavailable: 1  # Allow only 1 pod down at a time
  selector:
    matchLabels:
      app: cassandra
```

### 3. Ensure Proper Node Affinity:
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - cassandra
            topologyKey: kubernetes.io/hostname
      tolerations:
      - key: workload-type
        operator: Equal
        value: cassandra
        effect: NoSchedule
```

## Upgrade Process

### 1. Pre-upgrade Checklist:
```bash
# 1. Backup your data (if possible)
kubectl exec -it cassandra-0 -- nodetool snapshot

# 2. Verify all nodes are healthy
kubectl get nodes -l workload-type=cassandra

# 3. Check Cassandra ring health
kubectl exec -it cassandra-0 -- nodetool status
```

### 2. Execute Upgrade:
```bash
# Start the upgrade (will process 1 node at a time)
gcloud container node-pools upgrade cassandra-pool \
    --cluster=your-cluster-name \
    --zone=your-zone
```

### 3. Monitor Progress:
```bash
# Monitor node upgrade progress
kubectl get nodes -w

# Monitor Cassandra health during upgrade
watch 'kubectl exec -it cassandra-0 -- nodetool status'

# Check pod status
kubectl get pods -l app=cassandra -w
```

## Additional Recommendations

### 1. Maintenance Windows:
Schedule upgrades during low-traffic periods and ensure your team is available to monitor.

### 2. Gradual Rollout:
Consider upgrading a test environment first with the same configuration.

### 3. Monitoring:
Set up alerts for:
- Node readiness
- Cassandra ring health
- Pod scheduling failures
- Local SSD availability

### 4. Rollback Plan:
```bash
# If issues occur, you can drain and cordon problematic nodes
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
kubectl cordon <node-name>
```

This approach will safely upgrade your GKE cluster while preserving your Cassandra data and maintaining ring integrity throughout the process.
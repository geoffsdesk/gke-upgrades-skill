# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites & Safety Checklist

Before starting, ensure you have:
- [ ] `gcloud` CLI installed and authenticated
- [ ] `kubectl` configured for your cluster
- [ ] Backup/snapshot of critical data
- [ ] Maintenance window scheduled
- [ ] Team notified of potential downtime

## Step 1: Set Environment Variables

```bash
# Set your project and cluster details
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Verify these are correct
echo "Project: $PROJECT_ID"
echo "Cluster: $CLUSTER_NAME" 
echo "Zone: $ZONE"
```

## Step 2: Initial Assessment

### Check current cluster status:
```bash
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

### Get current versions:
```bash
# Control plane version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

# Node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(name,version,status)"
```

### Check available versions:
```bash
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID --format="yaml(validMasterVersions,validNodeVersions)"
```

### Verify node pool details:
```bash
kubectl get nodes -o wide
```

## Step 3: Pre-Upgrade Health Check

### Check cluster health:
```bash
# Check node status
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check for any failing pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check cluster events for issues
kubectl get events --sort-by=.metadata.creationTimestamp
```

### Document current workloads:
```bash
# List all deployments
kubectl get deployments --all-namespaces

# List all services
kubectl get services --all-namespaces

# Check PodDisruptionBudgets (important for upgrade safety)
kubectl get pdb --all-namespaces
```

## Step 4: Upgrade Control Plane

⚠️ **Note**: Control plane upgrades cause brief API server downtime (1-3 minutes)

```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --quiet
```

### Monitor the upgrade:
```bash
# Check upgrade status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME" --zone=$ZONE --project=$PROJECT_ID

# Wait for completion (5-10 minutes typically)
# You can also check in the GCP Console
```

### Verify control plane upgrade:
```bash
# Confirm new control plane version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

# Test API connectivity
kubectl get nodes
```

## Step 5: Upgrade Node Pools

⚠️ **Important**: Node pool upgrades will drain and recreate nodes, causing pod restarts

### Upgrade default-pool:
```bash
# Start the upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --quiet
```

### Monitor default-pool upgrade:
```bash
# Watch nodes being replaced
watch kubectl get nodes

# Check pod status during upgrade
watch kubectl get pods --all-namespaces
```

Wait for default-pool upgrade to complete before proceeding.

### Upgrade workload-pool:
```bash
# Start the upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --quiet
```

### Monitor workload-pool upgrade:
```bash
# Watch the upgrade progress
watch kubectl get nodes

# Monitor for any pod issues
kubectl get pods --all-namespaces | grep -E "(Error|CrashLoop|Pending)"
```

## Step 6: Post-Upgrade Verification

### Verify all versions:
```bash
# Control plane version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

# All node versions
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type"

# Node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(name,version,status)"
```

### Health checks:
```bash
# All nodes ready
kubectl get nodes

# System pods healthy
kubectl get pods -n kube-system

# Check for any problematic pods
kubectl get pods --all-namespaces | grep -v -E "(Running|Completed)"

# Verify workload pods
kubectl get pods --all-namespaces -o wide
```

### Test application connectivity:
```bash
# List services
kubectl get services --all-namespaces

# Test a sample service (replace with your actual service)
# kubectl port-forward svc/your-service 8080:80 -n your-namespace
```

### Check cluster events:
```bash
kubectl get events --sort-by=.metadata.creationTimestamp | tail -20
```

## Step 7: Final Validation

### Confirm upgrade success:
```bash
echo "=== UPGRADE SUMMARY ==="
echo "Control Plane Version:"
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

echo ""
echo "Node Pool Versions:"
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(name,version,status)"

echo ""
echo "Node Status:"
kubectl get nodes --no-headers | wc -l
kubectl get nodes --no-headers | grep Ready | wc -l
```

## Troubleshooting Common Issues

### If nodes are stuck in upgrade:
```bash
# Check specific node events
kubectl describe node <node-name>

# Check for pod eviction issues
kubectl get pods --all-namespaces -o wide | grep <node-name>
```

### If pods won't start after upgrade:
```bash
# Check pod logs
kubectl logs <pod-name> -n <namespace>

# Describe pod for events
kubectl describe pod <pod-name> -n <namespace>

# Check resource constraints
kubectl top nodes
kubectl top pods --all-namespaces
```

### Emergency rollback (if needed):
```bash
# Note: You can only rollback node pools, not control plane
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=<pool-name> \
    --cluster-version=1.32 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

## Expected Timeline

- **Control plane upgrade**: 5-10 minutes
- **Each node pool upgrade**: 10-30 minutes (depends on node count)
- **Total expected time**: 20-60 minutes

## Success Criteria

- [ ] Control plane shows version 1.33
- [ ] All node pools show version 1.33  
- [ ] All nodes are in "Ready" status
- [ ] All system pods are running
- [ ] Application pods are running and accessible
- [ ] No critical errors in cluster events

The upgrade is complete when all criteria are met!
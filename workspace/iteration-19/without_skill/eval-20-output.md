# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Pre-Upgrade Checklist

### 1. Set Environment Variables
```bash
export CLUSTER_NAME="your-cluster-name"
export PROJECT_ID="your-project-id"
export ZONE="us-west1-b"
```

### 2. Authenticate and Set Context
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE

# Verify you're connected to the right cluster
kubectl config current-context
```

### 3. Pre-Upgrade Assessment
```bash
# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check available upgrade versions
gcloud container get-server-config --zone $ZONE --format="yaml(validMasterVersions)"

# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 4. Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup all resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
kubectl get pv -o yaml > persistent-volumes-backup.yaml
kubectl get pvc --all-namespaces -o yaml > persistent-volume-claims-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get ingress --all-namespaces -o yaml > ingress-backup.yaml

# List all custom resources (if any)
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found --all-namespaces > custom-resources-backup.yaml

cd ..
```

### 5. Document Current State
```bash
# Document current state
kubectl get nodes -o wide > pre-upgrade-nodes.txt
kubectl get pods --all-namespaces -o wide > pre-upgrade-pods.txt
kubectl top nodes > pre-upgrade-node-usage.txt || echo "Metrics server not available"
kubectl top pods --all-namespaces > pre-upgrade-pod-usage.txt || echo "Metrics server not available"
```

## Upgrade Process

### Phase 1: Control Plane Upgrade

#### 1. Initiate Control Plane Upgrade
```bash
# Upgrade the control plane to 1.33
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone $ZONE \
    --master \
    --cluster-version "1.33" \
    --quiet

# Monitor the upgrade progress
echo "Control plane upgrade initiated. This may take 10-15 minutes."
echo "Monitoring upgrade status..."

# Check upgrade status (run this periodically)
while true; do
    STATUS=$(gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status)")
    VERSION=$(gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)")
    echo "$(date): Cluster status: $STATUS, Master version: $VERSION"
    
    if [[ "$STATUS" == "RUNNING" && "$VERSION" == "1.33"* ]]; then
        echo "Control plane upgrade completed successfully!"
        break
    fi
    
    if [[ "$STATUS" == "ERROR" ]]; then
        echo "ERROR: Upgrade failed!"
        exit 1
    fi
    
    sleep 30
done
```

#### 2. Verify Control Plane Upgrade
```bash
# Verify control plane version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl cluster-info
kubectl get nodes
```

### Phase 2: Node Pool Upgrades

#### 1. Upgrade default-pool
```bash
echo "Starting upgrade of default-pool..."

# Check current node pool version
gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# List pods on nodes in default-pool (for monitoring)
kubectl get pods --all-namespaces -o wide | grep -E "$(kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o jsonpath='{.items[*].metadata.name}' | tr ' ' '|')" > default-pool-pods-before.txt

# Start the node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone $ZONE \
    --node-pool default-pool \
    --cluster-version "1.33" \
    --quiet

# Monitor upgrade progress
echo "Node pool upgrade initiated. This may take 20-30 minutes."
echo "Monitoring upgrade status..."

while true; do
    POOL_STATUS=$(gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status)")
    POOL_VERSION=$(gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)")
    echo "$(date): default-pool status: $POOL_STATUS, version: $POOL_VERSION"
    
    if [[ "$POOL_STATUS" == "RUNNING" && "$POOL_VERSION" == "1.33"* ]]; then
        echo "default-pool upgrade completed successfully!"
        break
    fi
    
    if [[ "$POOL_STATUS" == "ERROR" ]]; then
        echo "ERROR: Node pool upgrade failed!"
        exit 1
    fi
    
    sleep 60
done
```

#### 2. Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check pod health
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Wait for all pods to be ready
echo "Waiting for all pods to be ready..."
kubectl wait --for=condition=Ready pods --all --all-namespaces --timeout=300s || echo "Some pods may still be starting"
```

#### 3. Upgrade workload-pool
```bash
echo "Starting upgrade of workload-pool..."

# Check current node pool version
gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# List pods on nodes in workload-pool (for monitoring)
kubectl get pods --all-namespaces -o wide | grep -E "$(kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o jsonpath='{.items[*].metadata.name}' | tr ' ' '|')" > workload-pool-pods-before.txt

# Start the node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone $ZONE \
    --node-pool workload-pool \
    --cluster-version "1.33" \
    --quiet

# Monitor upgrade progress
echo "Node pool upgrade initiated. This may take 20-30 minutes."
echo "Monitoring upgrade status..."

while true; do
    POOL_STATUS=$(gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status)")
    POOL_VERSION=$(gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)")
    echo "$(date): workload-pool status: $POOL_STATUS, version: $POOL_VERSION"
    
    if [[ "$POOL_STATUS" == "RUNNING" && "$POOL_VERSION" == "1.33"* ]]; then
        echo "workload-pool upgrade completed successfully!"
        break
    fi
    
    if [[ "$POOL_STATUS" == "ERROR" ]]; then
        echo "ERROR: Node pool upgrade failed!"
        exit 1
    fi
    
    sleep 60
done
```

#### 4. Verify workload-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check pod health
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Wait for all pods to be ready
echo "Waiting for all pods to be ready..."
kubectl wait --for=condition=Ready pods --all --all-namespaces --timeout=300s || echo "Some pods may still be starting"
```

## Post-Upgrade Verification

### 1. Comprehensive Health Check
```bash
# Verify all components are at 1.33
echo "=== CLUSTER VERSION VERIFICATION ==="
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

echo "=== NODE POOL VERSIONS ==="
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

echo "=== NODE STATUS ==="
kubectl get nodes -o wide

echo "=== POD STATUS ==="
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

echo "=== SYSTEM PODS STATUS ==="
kubectl get pods -n kube-system

echo "=== PERSISTENT VOLUMES ==="
kubectl get pv

echo "=== SERVICES STATUS ==="
kubectl get svc --all-namespaces
```

### 2. Application Connectivity Tests
```bash
# Test internal DNS
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local

# Test internet connectivity from cluster
kubectl run test-internet --image=busybox --rm -it --restart=Never -- wget -qO- http://httpbin.org/ip

# If you have ingress, test external connectivity
kubectl get ingress --all-namespaces
```

### 3. Performance Verification
```bash
# Check resource usage (if metrics-server is available)
kubectl top nodes || echo "Metrics server not available"
kubectl top pods --all-namespaces || echo "Metrics server not available"

# Check cluster events for any warnings
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### 4. Document Post-Upgrade State
```bash
# Document post-upgrade state
kubectl get nodes -o wide > post-upgrade-nodes.txt
kubectl get pods --all-namespaces -o wide > post-upgrade-pods.txt
kubectl top nodes > post-upgrade-node-usage.txt || echo "Metrics server not available"
kubectl top pods --all-namespaces > post-upgrade-pod-usage.txt || echo "Metrics server not available"

# Compare with pre-upgrade state
echo "=== NODE COUNT COMPARISON ==="
echo "Before: $(wc -l < pre-upgrade-nodes.txt)"
echo "After: $(wc -l < post-upgrade-nodes.txt)"

echo "=== POD COUNT COMPARISON ==="
echo "Before: $(wc -l < pre-upgrade-pods.txt)"
echo "After: $(wc -l < post-upgrade-pods.txt)"
```

## Troubleshooting Common Issues

### If Control Plane Upgrade Fails
```bash
# Check cluster status and events
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE
gcloud logging read "resource.type=gke_cluster resource.labels.cluster_name=$CLUSTER_NAME" --limit=50 --format="table(timestamp,severity,jsonPayload.message)"
```

### If Node Pool Upgrade Fails
```bash
# Check node pool status
gcloud container node-pools describe <POOL_NAME> --cluster $CLUSTER_NAME --zone $ZONE

# Check for stuck nodes
kubectl get nodes | grep -E "(NotReady|SchedulingDisabled)"

# Force drain stuck node if needed (use with caution)
# kubectl drain <NODE_NAME> --ignore-daemonsets --delete-emptydir-data --force
```

### If Pods Won't Start
```bash
# Check pod events
kubectl describe pod <POD_NAME> -n <NAMESPACE>

# Check resource constraints
kubectl describe nodes

# Check for image pull issues
kubectl get events --all-namespaces | grep -i "pull"
```

## Rollback Procedure (Emergency Only)

⚠️ **Warning**: GKE control plane cannot be downgraded. Only node pools can be managed for rollback scenarios.

```bash
# If you need to rollback node pools (this will recreate nodes)
# gcloud container node-pools rollback <POOL_NAME> --cluster $CLUSTER_NAME --zone $ZONE
```

## Success Criteria

✅ The upgrade is successful when:
- Control plane version shows 1.33.x
- Both node pools show version 1.33.x
- All nodes are in Ready state
- All critical pods are Running
- Applications are accessible
- No error events in the last 10 minutes

## Final Steps

1. **Clean up test resources**:
```bash
kubectl delete pod test-dns --ignore-not-found
kubectl delete pod test-internet --ignore-not-found
```

2. **Archive upgrade logs**:
```bash
# Create upgrade report
cat > upgrade-report.txt << EOF
GKE Cluster Upgrade Report
Date: $(date)
Cluster: $CLUSTER_NAME
Zone: $ZONE
Upgrade: 1.32 -> 1.33

Control Plane Version: $(gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)")
Node Pool Versions:
$(gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE --format="table(name,version)")

Status: SUCCESS
EOF

echo "Upgrade completed successfully!"
echo "Report saved to upgrade-report.txt"
```

3. **Notify stakeholders** that the upgrade is complete and applications are verified to be working.

---

**Total Expected Duration**: 45-90 minutes depending on cluster size and workload complexity.

**Next Steps**: Monitor the cluster for 24-48 hours and plan for the next upgrade cycle based on your Regular channel updates.
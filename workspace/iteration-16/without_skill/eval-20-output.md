# GKE Standard Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `kubectl` configured to access your cluster
- `gcloud` CLI installed and authenticated
- Basic understanding of your application architecture
- Maintenance window planned (upgrades can take 30-60+ minutes)

## Phase 1: Pre-Upgrade Assessment

### Step 1: Verify Current Cluster State
```bash
# Get cluster information
gcloud container clusters describe [CLUSTER_NAME] --zone=us-west1-b

# Check current versions
kubectl get nodes -o wide

# Verify cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -E "(Pending|Error|CrashLoopBackOff)"

# Check available upgrade versions
gcloud container get-server-config --zone=us-west1-b
```

### Step 2: Document Current Configuration
```bash
# Export current node pool configurations
gcloud container node-pools describe default-pool --cluster=[CLUSTER_NAME] --zone=us-west1-b > default-pool-config.yaml
gcloud container node-pools describe workload-pool --cluster=[CLUSTER_NAME] --zone=us-west1-b > workload-pool-config.yaml

# List all workloads
kubectl get deployments --all-namespaces -o wide > current-deployments.txt
kubectl get daemonsets --all-namespaces -o wide > current-daemonsets.txt
kubectl get statefulsets --all-namespaces -o wide > current-statefulsets.txt
```

### Step 3: Backup Critical Resources
```bash
# Create backup directory
mkdir gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup cluster resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get persistentvolumes -o yaml > pv-backup.yaml
kubectl get persistentvolumeclaims --all-namespaces -o yaml > pvc-backup.yaml
```

## Phase 2: Control Plane Upgrade

### Step 4: Upgrade Control Plane
```bash
# Upgrade control plane to 1.33 (adjust version as needed)
gcloud container clusters upgrade [CLUSTER_NAME] \
    --master \
    --cluster-version=1.33.X-gke.Y \
    --zone=us-west1-b

# Monitor upgrade progress
gcloud container operations list --zone=us-west1-b

# Verify control plane upgrade
kubectl version --short
gcloud container clusters describe [CLUSTER_NAME] --zone=us-west1-b | grep currentMasterVersion
```

**⚠️ Wait for control plane upgrade to complete before proceeding (typically 10-15 minutes)**

## Phase 3: Node Pool Upgrades

### Step 5: Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster=[CLUSTER_NAME] --zone=us-west1-b | grep version

# Start node pool upgrade
gcloud container clusters upgrade [CLUSTER_NAME] \
    --node-pool=default-pool \
    --cluster-version=1.33.X-gke.Y \
    --zone=us-west1-b

# Monitor node upgrade progress
watch kubectl get nodes

# Check pods during upgrade
watch "kubectl get pods --all-namespaces | grep -E '(Pending|Error|CrashLoopBackOff|Terminating)'"
```

### Step 6: Upgrade workload-pool
```bash
# Upgrade second node pool
gcloud container clusters upgrade [CLUSTER_NAME] \
    --node-pool=workload-pool \
    --cluster-version=1.33.X-gke.Y \
    --zone=us-west1-b

# Monitor upgrade progress
watch kubectl get nodes

# Verify all nodes are ready
kubectl get nodes -o wide
```

## Phase 4: Post-Upgrade Verification

### Step 7: Comprehensive Health Checks
```bash
# Verify all nodes are at correct version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check cluster component health
kubectl get componentstatuses

# Verify all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any failed deployments
kubectl get deployments --all-namespaces -o wide

# Test cluster DNS
kubectl run test-dns --image=busybox:1.28 --rm -it --restart=Never -- nslookup kubernetes.default

# Check cluster autoscaler (if enabled)
kubectl get events --all-namespaces | grep -i "cluster-autoscaler"
```

### Step 8: Application-Specific Testing
```bash
# Test application connectivity (replace with your app details)
kubectl get services --all-namespaces

# Check ingress controllers
kubectl get ingress --all-namespaces

# Verify persistent storage
kubectl get pv,pvc --all-namespaces

# Check for any resource warnings
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### Step 9: Performance Verification
```bash
# Check resource utilization
kubectl top nodes
kubectl top pods --all-namespaces

# Verify cluster info
kubectl cluster-info

# Check for any deprecated API usage
kubectl get events --all-namespaces | grep -i deprecat
```

## Phase 5: Final Validation

### Step 10: Complete System Check
```bash
# Final version confirmation
gcloud container clusters describe [CLUSTER_NAME] --zone=us-west1-b | grep -E "(currentMasterVersion|currentNodeVersion)"

# Verify node pool versions
gcloud container node-pools list --cluster=[CLUSTER_NAME] --zone=us-west1-b

# Check all system pods
kubectl get pods --all-namespaces -o wide | grep kube-system

# Validate networking
kubectl get networkpolicies --all-namespaces
kubectl get endpoints --all-namespaces
```

## Troubleshooting Commands

### If nodes are stuck in upgrade:
```bash
# Check upgrade status
gcloud container operations list --zone=us-west1-b

# Describe operation for details
gcloud container operations describe [OPERATION_ID] --zone=us-west1-b

# Force cordon/drain if needed
kubectl cordon [NODE_NAME]
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data --force
```

### If pods won't reschedule:
```bash
# Check pod disruption budgets
kubectl get pdb --all-namespaces

# Check node taints and tolerations
kubectl describe node [NODE_NAME] | grep -i taint

# Manually restart stuck deployments
kubectl rollout restart deployment [DEPLOYMENT_NAME] -n [NAMESPACE]
```

## Rollback Plan (Emergency Only)
```bash
# Note: Control plane cannot be rolled back, only node pools
# Roll back node pool if critical issues arise
gcloud container clusters upgrade [CLUSTER_NAME] \
    --node-pool=[POOL_NAME] \
    --cluster-version=1.32.X-gke.Y \
    --zone=us-west1-b
```

## Important Notes:
1. **Replace placeholders**: `[CLUSTER_NAME]`, `[POOL_NAME]`, specific version numbers
2. **Timing**: Full upgrade typically takes 45-90 minutes
3. **Disruption**: Expect brief pod disruptions during node upgrades
4. **Monitoring**: Keep monitoring dashboards open throughout the process
5. **Regular channel**: Future upgrades will be automatic unless you change channels

## Success Criteria:
- [ ] All nodes showing version 1.33.X
- [ ] All pods in Running/Completed state
- [ ] Applications responding normally
- [ ] No degraded services
- [ ] Cluster passes all health checks

Save all command outputs and keep this runbook for future reference!
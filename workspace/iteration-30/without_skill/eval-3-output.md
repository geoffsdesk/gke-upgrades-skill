This is a common GKE node pool upgrade issue. Let's diagnose and fix it step by step:

## 1. Check Node Pool Upgrade Status

```bash
# Get detailed upgrade status
kubectl get nodes -o wide
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Check specific node pool status
gcloud container node-pools describe <NODE_POOL_NAME> \
  --cluster=<CLUSTER_NAME> --zone=us-east1
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted. Check for:

```bash
# Find pods that are blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check for PodDisruptionBudgets that might be too restrictive
kubectl get pdb --all-namespaces

# Look for pods with local storage or no replica sets
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Unknown|Error)"
```

## 3. Common Blocking Scenarios

**A. Restrictive PodDisruptionBudgets:**
```bash
# Check PDB details
kubectl describe pdb --all-namespaces

# Temporarily relax PDB if safe to do so
kubectl patch pdb <PDB_NAME> -n <NAMESPACE> -p '{"spec":{"minAvailable":0}}'
```

**B. DaemonSets or StatefulSets:**
```bash
# Check for problematic DaemonSets
kubectl get daemonsets --all-namespaces

# Check StatefulSets
kubectl get statefulsets --all-namespaces
```

**C. Pods with local storage:**
```bash
# Find pods with emptyDir or hostPath volumes
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].hostPath.path}{"\n"}{end}'
```

## 4. Force Resolution

**Option 1: Manual pod eviction**
```bash
# Cordon the stuck nodes first
kubectl cordon <NODE_NAME>

# Manually drain specific nodes
kubectl drain <NODE_NAME> --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

**Option 2: Cancel and retry upgrade**
```bash
# Cancel current upgrade
gcloud container operations cancel <OPERATION_ID>

# Retry with different strategy
gcloud container node-pools upgrade <NODE_POOL_NAME> \
  --cluster=<CLUSTER_NAME> \
  --zone=us-east1 \
  --max-unavailable=1  # More conservative approach
```

## 5. Advanced Troubleshooting

**Check cluster events:**
```bash
kubectl get events --sort-by='.lastTimestamp' -A | tail -20
```

**Review node conditions:**
```bash
kubectl describe nodes | grep -A5 -B5 "Conditions\|Taints"
```

**Check for resource constraints:**
```bash
# Verify cluster has capacity for new nodes
kubectl top nodes
kubectl describe nodes | grep -A5 "Allocated resources"
```

## 6. Prevention for Future Upgrades

```bash
# Use surge upgrades for faster, more reliable upgrades
gcloud container node-pools update <NODE_POOL_NAME> \
  --cluster=<CLUSTER_NAME> \
  --zone=us-east1 \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=0
```

## Quick Fix Commands

If you need immediate resolution:

```bash
# 1. Get the stuck operation ID
OPERATION_ID=$(gcloud container operations list --filter="status=RUNNING AND operationType=UPGRADE_NODES" --format="value(name)")

# 2. Cancel the operation
gcloud container operations cancel $OPERATION_ID

# 3. Manual drain of remaining old nodes
kubectl get nodes --no-headers | grep "v1.31" | awk '{print $1}' | xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data --force

# 4. Restart upgrade with conservative settings
gcloud container node-pools upgrade <NODE_POOL_NAME> \
  --cluster=<CLUSTER_NAME> \
  --zone=us-east1 \
  --max-unavailable=1
```

The most likely culprit is restrictive PodDisruptionBudgets or pods with local storage that can't be safely evicted. Start with checking PDBs and manually draining the problematic nodes.
# GKE Node Pool Upgrade Troubleshooting Guide

## Problem Summary
- **Cluster**: Standard cluster in us-east1
- **Current version**: 1.29
- **Target version**: 1.30
- **Status**: Stuck at 3/12 nodes upgraded (2 hours elapsed)
- **Issue**: Pods not draining on remaining 9 nodes

## Root Cause Analysis

When a node pool upgrade stalls with incomplete node progression and stuck pods, the issue almost always relates to **pod eviction failures** during the drain phase. The upgrade process uses cordon-and-drain mechanics: nodes are cordoned (no new pods), then existing pods must be evicted/drained before the node is removed from the pool.

## Troubleshooting Walkthrough

### Step 1: Verify Node Status and Drain Conditions

```bash
# Get node pool upgrade details
gcloud container operations list --zone us-east1-b --filter="status!=DONE"

# Detailed node pool status
gcloud container node-pools describe default-pool \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b

# Check node conditions - look for cordoned nodes with NotReady conditions
kubectl get nodes -o wide
kubectl describe nodes | grep -A 10 "Conditions:"

# Identify cordoned nodes
kubectl get nodes -o json | jq '.items[] | select(.spec.unschedulable==true) | .metadata.name'
```

### Step 2: Investigate Pod Eviction Failures

**Common reasons pods won't drain:**

1. **Pods without controllers** (orphaned pods)
   ```bash
   # Find pods not managed by Deployment, StatefulSet, DaemonSet, etc.
   kubectl get pods -A -o json | jq '.items[] | select(.metadata.ownerReferences | length==0) | {name:.metadata.name, namespace:.metadata.namespace, node:.spec.nodeName}'
   ```

2. **PodDisruptionBudgets (PDBs) blocking eviction**
   ```bash
   # List all PDBs and their status
   kubectl get pdb -A
   kubectl describe pdb -n NAMESPACE PDB_NAME

   # Check if PDB is too restrictive
   kubectl get pdb -A -o json | jq '.items[] | {name:.metadata.name, namespace:.metadata.namespace, minAvailable:.spec.minAvailable, maxUnavailable:.spec.maxUnavailable}'
   ```

3. **Local storage or hostPath volumes**
   ```bash
   # Find pods with local storage
   kubectl get pods -A -o json | jq '.items[] | select(.spec.volumes[]? | select(.emptyDir!=null or .hostPath!=null)) | {name:.metadata.name, namespace:.metadata.namespace, node:.spec.nodeName}'
   ```

4. **Pods with `do-not-evict` or critical annotations**
   ```bash
   kubectl get pods -A -o json | jq '.items[] | select(.metadata.annotations."cluster-autoscaler.kubernetes.io/safe-to-evict"=="false") | {name:.metadata.name, namespace:.metadata.namespace}'
   ```

5. **Stuck terminating pods** (grace period exceeded)
   ```bash
   # Find pods in Terminating state for extended periods
   kubectl get pods -A --field-selector=status.phase=Failed,status.reason=NodeLost
   kubectl get pods -A -o json | jq '.items[] | select(.metadata.deletionTimestamp!=null) | {name:.metadata.name, namespace:.metadata.namespace, deletingFor:(.metadata.deletionTimestamp)}'
   ```

### Step 3: Check Node Pool Configuration

```bash
# Review node pool settings that affect drains
gcloud container node-pools describe default-pool \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b \
  --format="table(config.oauthScopes,config.machineType,config.diskSizeGb,initialNodeCount,nodeConfig.tags)"

# Check upgrade settings specifically
gcloud container node-pools describe default-pool \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b \
  --format="yaml" | grep -A 5 "upgrade"
```

### Step 4: Examine Cluster Events and Logs

```bash
# Get recent events related to node operations
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "drain\|evict\|cordoned"

# Check kubelet logs on cordoned nodes (if accessible via SSH/serial console)
# This requires enabling serial port access on instances

# Check if there are PVC-related issues (orphaned PVs)
kubectl get pvc -A | grep -v "Bound"
kubectl get pv | grep -v "Bound"
```

### Step 5: Check for Known Issues and Quotas

```bash
# Verify API quotas aren't being hit
gcloud compute project-info describe --format="value(quotas[name='INSTANCES'].usage)"

# Check if there are firewall or network policy issues
gcloud compute firewall-rules list --filter="disabled:false" | grep -i "ingress\|egress"

# Verify service account permissions
gcloud container clusters describe CLUSTER_NAME --zone=us-east1-b --format="value(nodeConfig.serviceAccount)"

# Check for resource quotas in namespaces that might be blocking evictions
kubectl get resourcequota -A -o wide
```

### Step 6: Application-Level Investigation

```bash
# Check for applications that resist graceful shutdown
kubectl logs -n NAMESPACE POD_NAME --tail=100 | grep -i "signal\|term\|shutdown\|exit"

# Look for stuck connections or long-lived operations
kubectl get pods -A -o json | jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {name:.metadata.name, terminationGracePeriod:.spec.terminationGracePeriodSeconds}'

# Check for init containers or lifecycle hooks that might be hanging
kubectl get pods -A -o json | jq '.items[].spec | {initContainers, lifecycle}'
```

## Resolution Strategies

### Quick Fix Options (In Priority Order)

#### Option 1: Force Evict Problematic Pods
```bash
# For pods that won't drain gracefully (ONLY if safe for your application)
kubectl delete pod -n NAMESPACE POD_NAME --grace-period=0 --force

# Or in batch for cordoned nodes
for pod in $(kubectl get pods -A --field-selector=status.phase=Pending -o jsonpath='{.items[*].metadata.name}'); do
  kubectl delete pod $pod -n $(kubectl get pod $pod -A -o jsonpath='{.metadata.namespace}') --grace-period=0 --force
done
```

#### Option 2: Relax PodDisruptionBudgets Temporarily
```bash
# If PDB is the bottleneck, increase unavailable allowance
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"maxUnavailable":"50%"}}'

# Increase minAvailable for less restrictive setup
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"minAvailable":0}}'
```

#### Option 3: Delete Orphaned Pods
```bash
# For pods without owner references (safe to delete)
kubectl delete pod -n NAMESPACE POD_NAME
```

#### Option 4: Increase Termination Grace Period
```bash
# If pods need more time to gracefully shut down
kubectl set env deployment/APP_NAME TERMINATION_GRACE_PERIOD=600
kubectl patch deployment/APP_NAME -p '{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":600}}}}'
```

#### Option 5: Manually Drain Nodes
```bash
# Only use if the upgrade is truly stuck
gcloud container node-pools update default-pool \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b \
  --enable-autorepair

# Force drain specific node
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Then complete the upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --master-upgrade-disabled \
  --cluster-version=1.30 \
  --node-pool=default-pool
```

### Preferred Approach: Systematic Mitigation

1. **Identify the root cause** using Steps 1-6 above
2. **Address the specific blocker**:
   - Too-strict PDB? Temporarily relax it
   - Orphaned pods? Delete them
   - Local storage? Migrate application or add node toleration
   - Stuck terminating? Force delete with grace period 0
3. **Resume upgrade** by restarting the node pool upgrade operation
4. **Monitor drain progress**: Watch `kubectl get nodes` for NotReady status changing
5. **Verify on upgraded nodes**: Check application health, pod distribution

## Monitoring During Resume

```bash
# Watch node upgrade progress
watch -n 5 'gcloud container node-pools describe default-pool --cluster=CLUSTER_NAME --zone=us-east1-b --format="table(name,status,config.machineType)" && echo "---" && kubectl get nodes -L cloud.google.com/gke-nodepool'

# Monitor pod eviction in real-time
kubectl get pods -A -w --field-selector=status.phase=Terminating

# Track drain operation
kubectl get events -A -w | grep -i drain
```

## Prevention for Future Upgrades

1. **Set reasonable PodDisruptionBudgets**:
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: app-pdb
   spec:
     minAvailable: 1  # Allow some disruption
     selector:
       matchLabels:
         app: myapp
   ```

2. **Use StatefulSets/Deployments with proper controllers** instead of naked pods

3. **Configure graceful shutdown properly**:
   ```yaml
   terminationGracePeriodSeconds: 30  # Reasonable timeout
   lifecycle:
     preStop:
       exec:
         command: ["/bin/sh", "-c", "sleep 5 && /app/shutdown.sh"]
   ```

4. **Avoid local storage in cluster-wide upgrades**

5. **Schedule upgrades during maintenance windows** when you can manually intervene if needed

6. **Test upgrade procedures in staging environments** with identical workload patterns

## Summary

Node pool upgrades stall almost exclusively due to pod eviction failures. The fix involves:
1. Identifying why pods won't evict (PDB, orphaned pods, local storage, etc.)
2. Removing the specific blocker
3. Restarting the upgrade

In most cases, the root cause appears in the first 15 minutes of investigation. The 2-hour wait suggests something structural is blocking drains rather than a transient issue.

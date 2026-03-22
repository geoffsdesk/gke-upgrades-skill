This is a common GKE upgrade issue. Let's diagnose and fix the pod draining problem systematically:

## 1. First, Check Current Status

```bash
# Check node pool upgrade status
kubectl get nodes -o wide

# Check which nodes are cordoned/draining
kubectl get nodes --show-labels | grep -E "(SchedulingDisabled|Ready)"

# See detailed upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES"
```

## 2. Identify Stuck Pods

```bash
# Find pods on nodes being upgraded
kubectl get pods --all-namespaces -o wide | grep -E "node-name-pattern"

# Check for pods with disruption issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
kubectl get pods --all-namespaces --field-selector=status.phase=Pending
```

## 3. Common Causes & Solutions

### A. Pod Disruption Budgets (Most Common)
```bash
# Check PDBs that might be blocking drainage
kubectl get pdb --all-namespaces

# Look for PDBs with 0 allowed disruptions
kubectl describe pdb --all-namespaces
```

**Fix:** Temporarily relax or delete overly restrictive PDBs:
```bash
# Edit PDB to allow more disruptions
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"minAvailable":1}}'
```

### B. Pods Without Proper Disruption Handling
```bash
# Find pods that might not handle SIGTERM properly
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.terminationGracePeriodSeconds}{"\n"}{end}'
```

**Fix:** Force delete stubborn pods (use carefully):
```bash
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

### C. Local Storage or hostPath Volumes
```bash
# Check for pods with local storage
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes}{"\n"}{end}' | grep -i "hostpath\|local"
```

## 4. Quick Resolution Steps

### Option 1: Manual Intervention (Fastest)
```bash
# 1. Identify problematic pods
kubectl get pods --all-namespaces --field-selector=spec.nodeName=<stuck-node-name>

# 2. Force delete pods that won't drain (backup approach)
kubectl delete pods --all-namespaces --field-selector=spec.nodeName=<stuck-node-name> --force --grace-period=0

# 3. Check if node can now drain
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force
```

### Option 2: Temporarily Modify PDBs
```bash
# Find restrictive PDBs
kubectl get pdb --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable

# Temporarily increase maxUnavailable
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"maxUnavailable":"50%"}}'
```

### Option 3: Pause and Resume Upgrade
```bash
# Get the operation ID
gcloud container operations list --filter="status=RUNNING"

# Cancel current operation (if safe to do so)
gcloud container operations cancel <OPERATION_ID> --region=us-east1

# Resume with different strategy
gcloud container node-pools upgrade <pool-name> \
    --cluster=<cluster-name> \
    --region=us-east1 \
    --node-version=1.32 \
    --max-surge=1 \
    --max-unavailable=0
```

## 5. Prevention for Future Upgrades

```bash
# Set better upgrade parameters
gcloud container node-pools update <pool-name> \
    --cluster=<cluster-name> \
    --region=us-east1 \
    --max-surge=2 \
    --max-unavailable=1
```

## 6. Monitor Progress

```bash
# Watch the upgrade progress
watch kubectl get nodes

# Monitor pod movements
kubectl get events --sort-by=.metadata.creationTimestamp
```

**Immediate Action Plan:**
1. Check PDBs first (most likely culprit)
2. If PDBs are blocking, temporarily relax them
3. Force delete any truly stuck pods
4. Monitor node drainage progress
5. Restore original PDB settings once upgrade completes

Would you like me to help you run any of these specific commands or dive deeper into any particular area?
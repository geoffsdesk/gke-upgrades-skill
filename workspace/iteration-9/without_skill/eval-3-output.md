This is a common issue with GKE node pool upgrades getting stuck during pod draining. Let's diagnose and fix this systematically:

## 1. Check Pod Draining Issues

First, identify which pods are preventing the drain:

```bash
# Check nodes in the upgrading pool
kubectl get nodes -o wide

# Look for nodes with SchedulingDisabled status
kubectl describe nodes | grep -A 5 -B 5 "SchedulingDisabled\|Unschedulable"

# Check for pods that can't be evicted
kubectl get pods --all-namespaces --field-selector spec.nodeName=NODE_NAME

# Look for eviction events
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -i evict
```

## 2. Common Culprits to Check

**Pod Disruption Budgets (PDBs):**
```bash
# Check PDBs that might be blocking eviction
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces

# Look for PDBs with 0 allowed disruptions
kubectl get pdb --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.disruptionsAllowed}{"\n"}{end}'
```

**DaemonSets:**
```bash
# DaemonSets can prevent node draining
kubectl get ds --all-namespaces
```

**Local Storage/hostPath volumes:**
```bash
# Check for pods with local storage that can't be moved
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.volumes[*].hostPath.path}{"\n"}{end}' | grep -v "^$"
```

## 3. Immediate Fixes

**Option A: Fix restrictive PDBs temporarily**
```bash
# Temporarily increase minAvailable or decrease maxUnavailable
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":2}}'
```

**Option B: Delete blocking pods manually**
```bash
# Force delete stuck pods (use cautiously)
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

**Option C: Cordon and drain manually**
```bash
# Manual drain with more aggressive settings
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=60
```

## 4. GKE-Specific Solutions

**Check upgrade status:**
```bash
# Get detailed upgrade status
gcloud container operations list --region=us-east1

# Describe the stuck operation
gcloud container operations describe OPERATION_ID --region=us-east1
```

**Cancel and restart upgrade (if necessary):**
```bash
# Cancel current upgrade (last resort)
gcloud container operations cancel OPERATION_ID --region=us-east1

# Wait a few minutes, then restart
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --region=us-east1 \
    --node-version=1.32
```

## 5. Prevention for Future Upgrades

**Set proper PDBs:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  maxUnavailable: 25%  # Allow some disruption
  selector:
    matchLabels:
      app: my-app
```

**Use surge upgrades:**
```bash
# Configure node pool for better upgrades
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --region=us-east1 \
    --max-surge=2 \
    --max-unavailable=0
```

## 6. Emergency Workaround

If the upgrade is critical and stuck:

```bash
# Scale down problematic deployments temporarily
kubectl scale deployment DEPLOYMENT_NAME -n NAMESPACE --replicas=0

# Wait for drain to complete, then scale back up
kubectl scale deployment DEPLOYMENT_NAME -n NAMESPACE --replicas=ORIGINAL_COUNT
```

## What to Check Right Now:

1. Run the PDB check command first - this is the most common cause
2. Look for any pods with `Terminating` status that won't die
3. Check if you have any stateful workloads with strict anti-affinity rules
4. Verify if there are any custom admission controllers blocking evictions

Start with the PDB investigation, as overly restrictive disruption budgets cause 80% of these stuck upgrade scenarios. Let me know what you find!
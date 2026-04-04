This is a common GKE upgrade issue. Let's diagnose and fix the stuck node pool upgrade systematically:

## 1. Check Pod Disruption Issues

First, identify what's preventing pods from draining:

```bash
# Check pods that might be blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# Look for pods with disruption budgets
kubectl get pdb --all-namespaces

# Check for pods without proper owners (naked pods)
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.ownerReferences[0].kind}{"\n"}{end}' | grep -E '\t\t|\tnull'
```

## 2. Common Blocking Issues & Fixes

**Pod Disruption Budgets (PDBs):**
```bash
# Check restrictive PDBs
kubectl get pdb --all-namespaces -o yaml | grep -A5 -B5 "minAvailable\|maxUnavailable"

# Temporarily relax overly restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":1}}'
```

**Naked Pods (no controller):**
```bash
# Delete naked pods (they won't be recreated)
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
```

**Local Storage or hostPath volumes:**
```bash
# Check for pods with local storage
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].hostPath.path}{"\n"}{end}' | grep -v "^[[:space:]]*$"
```

## 3. Check Node Conditions

```bash
# Check node status and conditions
kubectl get nodes -o wide

# Check specific node details
kubectl describe node <node-name>

# Look for scheduling issues
kubectl get events --sort-by='.lastTimestamp' | grep -i "failed\|error"
```

## 4. Force Progress (if needed)

**Option A: Manually drain problematic nodes**
```bash
# Drain with aggressive settings
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --grace-period=0
```

**Option B: Use gcloud to force upgrade continuation**
```bash
# Check upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Get detailed operation info
gcloud container operations describe <operation-id> --region=us-east1

# If safe, you can try to complete the upgrade
gcloud container node-pools upgrade <node-pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --node-version=1.32 \
  --max-unavailable=2  # Increase parallel upgrades
```

## 5. Emergency Procedures

**If completely stuck, consider canceling and restarting:**
```bash
# Cancel the current upgrade (if supported)
gcloud container operations cancel <operation-id> --region=us-east1

# Or create a new node pool and migrate
gcloud container node-pools create new-pool \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --node-version=1.32 \
  --machine-type=<current-machine-type> \
  --num-nodes=<desired-nodes>
```

## 6. Prevention for Future Upgrades

```bash
# Set better upgrade settings
gcloud container node-pools update <node-pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --max-unavailable=3 \
  --max-surge=2
```

## Immediate Action Plan:

1. **First**, check for restrictive PDBs - this is the #1 cause
2. **Second**, look for naked pods without controllers
3. **Third**, manually drain the most problematic nodes
4. **If desperate**, increase `--max-unavailable` to speed up the process

Start with the PDB check - that's likely your culprit. Let me know what you find and I can provide more specific guidance!
# GKE Upgrade Troubleshooting

Systematic diagnosis and resolution for stuck or failing GKE upgrades. Work through checks in priority order -- the first items are the most common causes.

## 1. PDB Blocking Drain (Most Common)

**Diagnose:**
```bash
# Find PDBs allowing zero disruptions
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Get details on blocking PDB
kubectl describe pdb PDB_NAME -n NAMESPACE

# Check Cloud Logging for eviction failures
# Filter: resource.type="k8s_node" "Cannot evict pod as it would violate the pod's disruption budget"
```

**Fix -- temporarily relax the PDB:**
```bash
# Option A: Allow all disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Option B: Back up, edit, restore after upgrade
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
kubectl delete pdb PDB_NAME -n NAMESPACE
# ... wait for drain to proceed ...
kubectl apply -f pdb-backup.yaml
```

**Important:** Restore original PDB settings after upgrade completes.

## 2. Resource Constraints

**Diagnose:**
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

**Fix -- increase surge capacity:**
```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

Or temporarily scale down non-critical workloads to free capacity.

## 3. Bare Pods (No Controller)

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences == null or (.metadata.ownerReferences | length == 0)) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods (they won't reschedule anyway) or wrap them in Deployments/Jobs.

## 4. Admission Webhooks Blocking Pod Creation

**Diagnose:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Check for webhooks matching broad API groups
kubectl get validatingwebhookconfigurations -o json | \
  jq '.items[] | {name: .metadata.name, rules: [.webhooks[].rules[].apiGroups]}'

# Check webhook endpoint availability
kubectl get endpoints -n NAMESPACE WEBHOOK_SERVICE
```

**Fix:**
```bash
# Temporarily set failure policy to Ignore
kubectl patch validatingwebhookconfiguration WEBHOOK_NAME \
  --type='json' -p='[{"op":"replace","path":"/webhooks/0/failurePolicy","value":"Ignore"}]'

# Or delete and recreate after upgrade
kubectl delete validatingwebhookconfiguration WEBHOOK_NAME
```

## 5. PVC Attachment Issues

**Diagnose:**
```bash
kubectl get pvc -A | grep -v Bound
kubectl get events -A --field-selector reason=FailedAttachVolume
kubectl get pv -o custom-columns=NAME:.metadata.name,ZONE:.spec.nodeAffinity
```

**Fix:** Zone-locked PVs can't migrate. Either migrate workloads to already-upgraded nodes in the same zone, or use regional persistent disks for cross-zone mobility.

## 6. Long Termination Grace Periods

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 120) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

**Fix:** GKE waits up to 1 hour for pod eviction during surge upgrades. If grace periods exceed this, reduce `terminationGracePeriodSeconds` in the workload spec.

## 7. GKE Operation Stuck

**Diagnose:**
```bash
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --filter="operationType=UPGRADE_NODES" \
  --limit=3
```

**Fix:** If no progress for >2 hours after resolving pod-level issues, contact GKE support with cluster name, zone, and operation ID.

## Validation After Applying Fix

```bash
# Monitor node upgrade progress
watch 'kubectl get nodes -o wide | sort -k5'

# Check no pods stuck
kubectl get pods -A | grep -E "Terminating|Pending"

# Confirm upgrade operation resumed
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1

# Verify node versions progressing
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,CREATED:.metadata.creationTimestamp
```

# Stuck Node Pool Upgrade Troubleshooting

Your node pool upgrade is stuck at 3/12 nodes after 2 hours, which indicates pods aren't draining from the remaining 9 nodes. Let's diagnose systematically:

## 1. Check PodDisruptionBudgets (most likely cause)

```bash
# Check all PDBs - look for ALLOWED = 0
kubectl get pdb -A -o wide

# Examine specific PDBs blocking drain
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**What to look for:** PDBs with `ALLOWED DISRUPTIONS: 0` are blocking eviction. Common culprits: databases, message queues, custom apps with overly restrictive PDBs.

**Fix:** Temporarily relax the blocking PDB:
```bash
# Option A: Allow 1 disruption temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"1"}}'

# Option B: Backup and edit if complex
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
# Edit minAvailable/maxUnavailable, apply, restore later
```

## 2. Check for bare pods (won't reschedule)

```bash
# Find pods without owner references
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check which nodes these pods are on
kubectl get pods -A -o wide | grep -E "pod-name-here"
```

**Fix:** Delete bare pods - they won't reschedule anyway:
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 3. Check resource constraints

```bash
# Look for pending pods (indicates no room to reschedule)
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling | tail -20

# Node resource utilization
kubectl top nodes
```

**Fix if quota-constrained:** Reduce maxSurge to free up capacity:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## 4. Check admission webhooks

```bash
# Look for webhooks that might reject pod creation
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Check recent webhook failures
kubectl get events -A --field-selector type=Warning | grep webhook
```

**Fix:** Temporarily set webhook failure policy to Ignore:
```bash
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK_NAME","failurePolicy":"Ignore"}]}'
```

## 5. Monitor upgrade progress

```bash
# Watch node status during upgrade
watch 'kubectl get nodes -o wide | grep -E "(NAME|1\.31|1\.32)"'

# Check current upgrade operation
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --filter="operationType=UPGRADE_NODES"
```

## 6. Resume upgrade after fixing

Once you've resolved the blocking issue (most likely PDB), the upgrade should resume automatically. If it doesn't after 10-15 minutes:

```bash
# Check if operation is still running
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --limit=1

# If stuck at GKE level after fixing pod issues, contact support
```

## Most likely scenario

Based on "pods aren't draining," this is almost certainly a **PDB issue**. Start with step 1 - check for PDBs with 0 allowed disruptions. Temporarily relax them, then restore the original settings after upgrade completes.

**Remember:** Save your original PDB configurations before modifying them:
```bash
kubectl get pdb -A -o yaml > all-pdbs-backup.yaml
```

Restore after upgrade:
```bash
kubectl apply -f all-pdbs-backup.yaml
```

Would you like me to help you check any specific applications or PDBs you know are running in the cluster?
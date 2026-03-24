# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Your Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Node pools:** default-pool, workload-pool  
**Location:** us-west1-b  

This runbook provides complete step-by-step commands for your first GKE upgrade.

## Pre-flight Checks (30 minutes)

### 1. Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and nodes should show 1.32.x
```

### 2. Confirm 1.33 is available in Regular channel
```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for 1.33.x versions in the output
```

### 3. Check for deprecated API usage (critical!)
```bash
# Check via kubectl (quick test)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE insights (comprehensive)
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=PROJECT_ID

# If you see deprecated API usage, STOP and fix before upgrading
```

### 4. Review cluster health
```bash
# All nodes should be Ready
kubectl get nodes -o wide

# No pods should be stuck
kubectl get pods -A | grep -E "CrashLoop|Pending|Error"

# System components healthy
kubectl get pods -n kube-system

# Check PDBs aren't overly restrictive
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN AVAILABLE:.spec.minAvailable,MAX UNAVAILABLE:.spec.maxUnavailable"
```

### 5. Verify workload protection
```bash
# Check for bare pods (these WON'T be rescheduled during upgrade)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# If you find bare pods, either delete them or create Deployments to manage them
```

## Configure Maintenance Settings (15 minutes)

### 6. Set maintenance window (recommended)
```bash
# Set weekend maintenance window (adjust timezone as needed)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-end "2024-01-20T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# This controls WHEN auto-upgrades happen. Manual upgrades (like this one) ignore the window.
```

### 7. Configure node pool surge settings
```bash
# For default-pool (assuming general workloads)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For workload-pool (assuming more sensitive workloads)
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# maxSurge=2 means create 2 extra nodes during upgrade
# maxUnavailable=0 means don't drain until replacement nodes exist
```

## Execute Upgrade (45-90 minutes total)

### 8. Upgrade control plane first (10-15 minutes)
```bash
# Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# Answer 'Y' when prompted
# This takes 10-15 minutes typically
```

### 9. Monitor control plane upgrade
```bash
# Check upgrade progress (run every few minutes)
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Wait until status shows DONE
```

### 10. Verify control plane upgraded
```bash
# Confirm control plane is at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Should show 1.33.x

# Check system pods restarted successfully
kubectl get pods -n kube-system
```

### 11. Upgrade first node pool (15-30 minutes)
```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Answer 'Y' when prompted
```

### 12. Monitor node pool upgrade progress
```bash
# Watch nodes being replaced (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|default-pool"'

# Check upgrade operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

### 13. Verify first node pool completed
```bash
# All default-pool nodes should show 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# No pods should be stuck
kubectl get pods -A | grep -E "Pending|Terminating"
```

### 14. Upgrade second node pool (15-30 minutes)
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Answer 'Y' when prompted
```

### 15. Monitor second node pool upgrade
```bash
# Watch workload-pool nodes being replaced
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|workload-pool"'

# Check for any stuck pods
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"
```

## Post-Upgrade Validation (15 minutes)

### 16. Verify complete cluster upgrade
```bash
# All components should show 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready at 1.33
kubectl get nodes -o wide

# All system pods healthy
kubectl get pods -n kube-system | grep -v Running
```

### 17. Test workload health
```bash
# All deployments at desired replica count
kubectl get deployments -A

# No failed pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Test a simple pod creation
kubectl run test-upgrade --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"
```

### 18. Verify application functionality
```bash
# Test your specific applications (customize these commands)
# Examples:
# curl http://YOUR_SERVICE_IP/health
# kubectl logs -f deployment/YOUR_APP_NAME
# kubectl exec -it deployment/YOUR_APP_NAME -- YOUR_HEALTH_CHECK_COMMAND
```

## Troubleshooting Common Issues

### If upgrade gets stuck with pods not draining:

```bash
# Check what's blocking drain
kubectl get pdb -A -o wide

# If PDB shows ALLOWED DISRUPTIONS = 0, temporarily relax it:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Remember to restore PDB after upgrade completes
```

### If you see "Insufficient resources" errors:

```bash
# Reduce surge to use less resources
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### If pods are stuck Pending:

```bash
# Check node capacity
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check for scheduling issues
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
```

## Rollback Plan (if needed)

If something goes wrong after the upgrade completes:

```bash
# You CANNOT downgrade the control plane from 1.33 back to 1.32
# Node pools can be rolled back by creating new pools at 1.32:

# Create new pool at old version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Delete old pool after verification
gcloud container node-pools delete POOL_NAME --cluster CLUSTER_NAME --zone us-west1-b
```

## Key Points for Your First Upgrade

1. **Control plane MUST be upgraded before nodes** — this is the required order
2. **Nodes can be up to 2 minor versions behind control plane** — 1.32 nodes work fine with 1.33 control plane
3. **Each node pool upgrades sequentially** — GKE won't start workload-pool until default-pool completes
4. **Surge nodes cost extra temporarily** — they're deleted after upgrade completes
5. **Manual upgrades ignore maintenance windows** — they start immediately when you run the command
6. **Mixed node versions are normal during upgrade** — some nodes at 1.32, others at 1.33 is expected and functional

**Total expected time:** 60-90 minutes depending on cluster size and number of pods to reschedule.

Replace `CLUSTER_NAME` with your actual cluster name in all commands above. Good luck with your first GKE upgrade! 🚀
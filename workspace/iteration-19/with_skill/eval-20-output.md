# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Your Standard cluster  
**Channel:** Regular  
**Current:** 1.32.x  
**Target:** 1.33.x  
**Pools:** default-pool, workload-pool

This runbook assumes you have basic `kubectl` knowledge and `gcloud` CLI installed with cluster access.

## ⚠️ Important Notes

- **Upgrade order:** Control plane MUST be upgraded before node pools
- **Version skew:** Nodes can't be newer than control plane
- **Downtime:** Control plane upgrade causes ~5-10 minutes of API unavailability (workloads keep running)
- **Node pool upgrades:** Rolling replacement — pods will restart as nodes upgrade

## Pre-Flight Checklist

### 1. Verify cluster access and current state

```bash
# Confirm cluster access
kubectl get nodes

# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

Expected output: Control plane and nodes at 1.32.x

### 2. Check available versions

```bash
# See what 1.33 versions are available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 10 "channel: REGULAR"
```

Pick the latest 1.33.x version from the "availableVersions" list.

### 3. Check for deprecated APIs (critical!)

```bash
# Check for deprecated API usage - this is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check in GKE Console: Clusters → Your Cluster → Insights tab → "Deprecations and Issues"
```

If deprecated APIs are found, fix them before proceeding. GKE will automatically pause auto-upgrades when deprecated APIs are detected.

### 4. Verify workload health

```bash
# Check all pods are running
kubectl get pods -A | grep -v Running | grep -v Completed

# Check no stuck PDBs (these can block node draining)
kubectl get pdb -A -o wide

# Check for bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix issues before proceeding:**
- Crashlooping pods should be investigated
- PDBs with ALLOWED DISRUPTIONS = 0 need to be relaxed
- Bare pods should be deleted or wrapped in Deployments

### 5. Take backups (if you have stateful workloads)

```bash
# List persistent volumes
kubectl get pv

# For databases/stateful apps, take application-level backups now
# Examples:
# - PostgreSQL: pg_dump
# - MySQL: mysqldump  
# - MongoDB: mongodump
```

## Phase 1: Control Plane Upgrade

### 1. Start control plane upgrade

```bash
# Replace TARGET_VERSION with the 1.33.x version from step 2 above
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version TARGET_VERSION

# Example: --cluster-version 1.33.1-gke.1234
```

You'll see: `Do you want to continue (Y/n)?` → Type `Y`

### 2. Monitor control plane upgrade

```bash
# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5

# Monitor until status shows DONE (typically 10-15 minutes)
```

**During this time:**
- Workloads continue running normally
- You cannot make API calls (deploy, scale, etc.)
- Don't panic if `kubectl` commands fail temporarily

### 3. Verify control plane upgrade

```bash
# Confirm control plane is at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods are healthy
kubectl get pods -n kube-system

# Verify API server is responsive
kubectl get nodes
```

Expected: Control plane at 1.33.x, nodes still at 1.32.x (this is normal!)

## Phase 2: Node Pool Upgrades

### 1. Configure upgrade strategy

We'll use surge upgrade (default) with conservative settings:

```bash
# Configure default-pool surge settings
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure workload-pool surge settings  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This creates 1 new node before draining 1 old node (safest approach).

### 2. Upgrade default-pool first

```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION
```

### 3. Monitor default-pool upgrade

```bash
# Watch node versions change (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|default-pool"'

# Check for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=3
```

**What you'll see:**
- New nodes appear with 1.33.x
- Old nodes get cordoned (SchedulingDisabled)
- Pods drain to new nodes
- Old nodes disappear

Wait until operation shows DONE before proceeding.

### 4. Upgrade workload-pool

```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|workload-pool"'
```

## Phase 3: Post-Upgrade Validation

### 1. Verify all versions upgraded

```bash
# Check final state - everything should be 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify all nodes
kubectl get nodes -o wide
```

### 2. Check workload health

```bash
# All pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# All deployments at desired replica count
kubectl get deployments -A

# No stuck PDBs
kubectl get pdb -A -o wide

# System components healthy
kubectl get pods -n kube-system
```

### 3. Application smoke tests

```bash
# Test your application endpoints
# Examples:
curl http://YOUR_SERVICE_IP/health
kubectl port-forward deployment/your-app 8080:80 &
curl http://localhost:8080/
```

## Troubleshooting Common Issues

### Node pool upgrade stuck

**Symptoms:** Nodes not draining, upgrade operation running for hours

**Diagnosis:**
```bash
# Check for blocking PDBs
kubectl get pdb -A -o wide

# Check pending pods
kubectl get pods -A | grep Pending

# Check drain events
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

**Fix:** Temporarily relax PDBs:
```bash
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Pods stuck terminating

**Diagnosis:**
```bash
kubectl get pods -A | grep Terminating
kubectl describe pod POD_NAME -n NAMESPACE
```

**Fix:** Force delete if stuck >10 minutes:
```bash
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### API server errors after upgrade

**Symptoms:** 503 errors, increased latency

**Check:**
```bash
# System pods health
kubectl get pods -n kube-system

# Deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Rollback (Emergency Only)

**Node pool rollback** (if workloads fail on 1.33):

```bash
# Create new pool at 1.32 version
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32.LATEST \
  --num-nodes 3 \
  --machine-type e2-standard-4

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL_NAME

# Manually drain workloads to rollback pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force
```

**Control plane rollback** requires GKE support - contact immediately if needed.

## Expected Timeline

- **Control plane upgrade:** 10-15 minutes
- **Each node pool upgrade:** 15-30 minutes (depends on node count)
- **Total:** 45-75 minutes for complete upgrade

## Success Criteria

✅ Control plane at 1.33.x  
✅ All node pools at 1.33.x  
✅ All nodes in Ready state  
✅ All workloads running normally  
✅ Application endpoints responding  

## Next Steps

1. **Document the upgrade** in your change log
2. **Update monitoring** if you track cluster versions
3. **Set maintenance windows** to control future auto-upgrades:
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone us-west1-b \
     --maintenance-window-start "2024-01-13T02:00:00Z" \
     --maintenance-window-end "2024-01-13T06:00:00Z" \
     --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
   ```
4. **Consider Regular → Stable channel** if you want slower upgrade cadence

## Emergency Contacts

- **Your team lead:** [Fill in]
- **Platform team:** [Fill in]  
- **GKE Support:** Create support case in Google Cloud Console

---

**Remember:** Replace `CLUSTER_NAME` and `TARGET_VERSION` with your actual values throughout this runbook. Take your time, validate each phase before proceeding, and don't hesitate to ask for help if something looks wrong.
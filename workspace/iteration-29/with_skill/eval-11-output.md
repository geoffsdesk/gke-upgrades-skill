# Elasticsearch Upgrade Plan: GKE 1.31 → 1.32

## Executive Summary
This plan covers upgrading a StatefulSet-based Elasticsearch cluster across 3 node pools with zero data loss and minimal availability impact. We'll use conservative surge settings and strict PDBs to protect Elasticsearch quorum during the upgrade.

## Cluster Configuration
- **Cluster:** Standard GKE
- **Current version:** 1.31
- **Target version:** 1.32
- **Architecture:** 3 masters + 5 data + 2 coordinators (separate node pools)
- **Storage:** Regional pd-ssd PVs

## Pre-Upgrade Checklist

### Compatibility & Planning
- [ ] Verify 1.32 available in your release channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- [ ] Check GKE 1.31→1.32 release notes for breaking changes
- [ ] Confirm Elasticsearch version compatibility with K8s 1.32
- [ ] Review deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`

### Elasticsearch-Specific Readiness
- [ ] **Cluster health green:** `curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"`
- [ ] **Disable shard allocation:** Prevent rebalancing during upgrade
  ```bash
  curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  ```
- [ ] **Application-level backup:** Take snapshot before upgrade
  ```bash
  curl -X PUT "elasticsearch-service:9200/_snapshot/backup-repo/pre-upgrade-snapshot?wait_for_completion=true"
  ```
- [ ] **Verify PV reclaim policy:** Ensure `Retain` not `Delete`
  ```bash
  kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
  ```

### PDB Configuration (Critical for Elasticsearch)
Configure strict PDBs to protect quorum during drain:

```bash
# Master nodes PDB - allow 1 master to drain, keep 2 for quorum
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
EOF

# Data nodes PDB - allow 1-2 data nodes to drain simultaneously
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app: elasticsearch
      role: data
EOF

# Coordinator nodes PDB - keep 1 available for client requests
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
EOF
```

## Upgrade Execution

### Step 1: Control Plane Upgrade

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait and verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Check system pods health
kubectl get pods -n kube-system | grep -v Running
```

### Step 2: Node Pool Upgrades (Sequential Order)

**Upgrade order: Coordinators → Data → Masters**
This minimizes disruption to search traffic and protects the master quorum last.

#### 2a. Coordinator Node Pool (Lowest Risk)

```bash
# Configure conservative surge settings
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l nodepool=coordinator-pool -o wide'

# Verify coordinators healthy
kubectl get pods -l role=coordinator -o wide
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
```

#### 2b. Data Node Pool (Moderate Risk)

```bash
# Configure surge settings
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor StatefulSet rollout
kubectl rollout status statefulset/elasticsearch-data -n elasticsearch --watch

# Verify data nodes rejoined cluster
kubectl get pods -l role=data -o wide
curl -X GET "elasticsearch-service:9200/_cat/nodes?v&h=name,node.role,version"
```

**Wait for data rebalancing:** After each data node rejoins, wait for cluster status to return to green before continuing.

#### 2c. Master Node Pool (Highest Risk - Most Conservative)

```bash
# Configure most conservative surge settings
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master StatefulSet carefully
kubectl rollout status statefulset/elasticsearch-master -n elasticsearch --watch

# Verify master election and quorum
kubectl logs -l role=master -n elasticsearch --tail=50 | grep -i "elected\|master"
curl -X GET "elasticsearch-service:9200/_cat/master?v"
```

### Step 3: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check Elasticsearch cluster health
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
# Should return: "status": "green", "number_of_nodes": 10

# Verify all expected nodes present
curl -X GET "elasticsearch-service:9200/_cat/nodes?v"

# Test search functionality
curl -X GET "elasticsearch-service:9200/_search?size=1&pretty"

# Re-enable shard allocation
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Monitor shard rebalancing
curl -X GET "elasticsearch-service:9200/_cat/shards?v&s=index"
```

## Rollback Plan (If Needed)

If issues arise during the upgrade:

### Option 1: Cancel In-Progress Node Pool Upgrade
```bash
# Check current operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Note: GKE will finish the current node before stopping
```

### Option 2: Create Rollback Node Pool
```bash
# Create new pool at 1.31
gcloud container node-pools create POOL-NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon problematic pool
kubectl cordon -l cloud.google.com/gke-nodepool=POOL-NAME

# Update StatefulSet nodeSelector to prefer rollback pool
# Then delete pods to trigger rescheduling
```

## Troubleshooting Common Issues

### Masters Won't Drain (PDB Blocking)
```bash
# Check PDB status
kubectl get pdb elasticsearch-master-pdb -o wide

# Temporarily relax if needed (emergency only)
kubectl patch pdb elasticsearch-master-pdb \
  -p '{"spec":{"minAvailable":1}}'
```

### Data Pods Stuck Terminating
```bash
# Check for persistent volume attachment issues
kubectl get events -A --field-selector reason=FailedAttachVolume

# Force delete stuck pods (last resort)
kubectl delete pod STUCK_POD --force --grace-period=0
```

### Cluster Status Yellow/Red During Upgrade
This is expected during data node upgrades. Monitor with:
```bash
# Watch cluster status
watch 'curl -s "elasticsearch-service:9200/_cluster/health" | jq .'

# Check unassigned shards
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

## Timeline Expectations

- **Control plane:** 10-15 minutes
- **Coordinator pool (2 nodes):** 20-30 minutes  
- **Data pool (5 nodes):** 1-2 hours (includes shard rebalancing wait time)
- **Master pool (3 nodes):** 45-60 minutes
- **Total:** 3-4 hours

## Key Success Factors

1. **PDBs are critical** - They prevent multiple Elasticsearch nodes from draining simultaneously
2. **Upgrade order matters** - Coordinators first, masters last to protect quorum
3. **Wait for green health** - After each pool, ensure cluster returns to green before continuing
4. **Conservative surge settings** - One node at a time for stateful workloads
5. **Disable shard allocation** - Prevents unnecessary rebalancing during the upgrade

The regional pd-ssd volumes will automatically reattach to new nodes, so data persistence is protected throughout the process.
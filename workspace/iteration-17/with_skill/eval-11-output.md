# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Overview
**Cluster:** GKE Standard  
**Current:** 1.31 → **Target:** 1.32  
**Workload:** Elasticsearch StatefulSet with 3 masters, 5 data nodes, 2 coordinators  
**Storage:** Regional pd-ssd PVs (survive node upgrades)  

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Elasticsearch Cluster
- [ ] Cluster health: `curl -X GET "localhost:9200/_cluster/health?pretty"`
- [ ] All shards allocated: `curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"`
- [ ] Elasticsearch version compatible with K8s 1.32 (check operator docs)
- [ ] PV reclaim policies are "Retain": `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`
- [ ] Elasticsearch snapshot backup completed: `curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot?wait_for_completion=true"`
- [ ] PDBs configured for each StatefulSet (see configuration below)
- [ ] No deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Maintenance window scheduled during off-peak hours
- [ ] On-call team available
```

## Elasticsearch-Specific PDB Configuration

Before upgrading, configure PDBs to protect quorum:

```bash
# Master nodes PDB (allow 1 disruption, maintain quorum of 2)
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

# Data nodes PDB (allow 2 disruptions, keep majority available)
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

# Coordinator nodes PDB (allow 1 disruption, keep 1 serving)
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

## Node Pool Surge Configuration

Configure conservative surge settings for stateful workloads:

```bash
# Master node pool - most critical, upgrade one at a time
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data node pool - allow 1 disruption (PDB protects the rest)
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Coordinator pool - less critical, can be more aggressive
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Upgrade Runbook

### Step 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane (wait 10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Confirm system pods healthy
kubectl get pods -n kube-system
```

### Step 2: Node Pool Upgrades (Sequential Order)

**Important:** Upgrade coordinators first (least critical), then data nodes, then masters last.

#### 2a. Coordinator Nodes First
```bash
# Monitor Elasticsearch health before starting
curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade coordinator pool
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=coordinator-pool -o wide'

# Verify coordinators rejoin cluster
kubectl get pods -l role=coordinator -o wide
curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,version"
```

#### 2b. Data Nodes Second
```bash
# Verify cluster is still green after coordinators
curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade data pool (one node at a time due to PDB)
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor data node upgrades and shard rebalancing
watch 'kubectl get pods -l role=data -o wide'
# Watch for shard rebalancing (may take time)
watch 'curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state" | grep -v STARTED'
```

#### 2c. Master Nodes Last
```bash
# Final health check before master upgrades
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cat/master?v"

# Upgrade master pool (most critical - one at a time)
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor master elections during upgrade
watch 'curl -s "localhost:9200/_cat/master?v"'
kubectl get pods -l role=master -o wide
```

### Step 3: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Elasticsearch cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,version,heap.percent,ram.percent"
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# No unassigned shards
curl -X GET "localhost:9200/_cat/shards?v" | grep -v STARTED | grep -v RELOCATED

# StatefulSet health
kubectl get statefulsets -n elasticsearch
kubectl get pods -n elasticsearch | grep -v Running

# PV attachments healthy
kubectl get pvc -n elasticsearch
```

## Monitoring During Upgrade

Run these checks between each node pool upgrade:

```bash
# Elasticsearch cluster status
curl -X GET "localhost:9200/_cluster/health?pretty" | jq '.status'  # Should be "green"

# Shard allocation
curl -X GET "localhost:9200/_cat/allocation?v&h=node,shards,disk.used_percent"

# No stuck relocating shards
curl -X GET "localhost:9200/_cat/shards?v" | grep RELOCATING | wc -l  # Should be 0

# Kubernetes pods
kubectl get pods -n elasticsearch -o wide | grep -E "Terminating|Pending|CrashLoopBackOff"
```

## Troubleshooting

### If cluster goes yellow/red during upgrade:
```bash
# Check which shards are unassigned
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Force shard allocation if needed (emergency only)
curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"

# Check node exclusions (shouldn't be set during upgrade)
curl -X GET "localhost:9200/_cluster/settings?pretty"
```

### If PDB blocks drain too aggressively:
```bash
# Temporarily relax data PDB to allow 2 disruptions
kubectl patch pdb elasticsearch-data-pdb -n elasticsearch \
  -p '{"spec":{"minAvailable":3}}'  # Allows 2 disruptions from 5 nodes

# Monitor and restore after upgrade
```

### If pods don't reschedule to new nodes:
```bash
# Check for affinity/anti-affinity rules
kubectl get pods -l role=data -o yaml | grep -A 10 affinity

# Verify PVC can attach to new zones
kubectl describe pvc DATA_PVC_NAME -n elasticsearch
```

## Rollback Strategy

If critical issues arise:
1. **Node pools**: Create new pools at 1.31, migrate workloads, delete problem pools
2. **Data protection**: Regional PVs survive node changes - data is safe
3. **Elasticsearch restore**: Use snapshot: `curl -X POST "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot/_restore"`

**Important**: Control plane cannot be easily rolled back from 1.32 to 1.31 without GKE support involvement.

## Expected Timeline

- **Control plane**: 10-15 minutes
- **Coordinator pool**: 15-20 minutes (2 nodes)  
- **Data pool**: 45-60 minutes (5 nodes, one at a time, with shard rebalancing)
- **Master pool**: 30-45 minutes (3 nodes, one at a time)
- **Total**: ~2-2.5 hours

**Key Success Factors:**
- Conservative surge settings (maxSurge=1) prevent multiple Elasticsearch nodes draining simultaneously
- PDBs ensure quorum is maintained throughout
- Regional PVs eliminate data loss risk
- Sequential upgrade order (coordinators → data → masters) minimizes disruption
- Monitoring between each pool catches issues early
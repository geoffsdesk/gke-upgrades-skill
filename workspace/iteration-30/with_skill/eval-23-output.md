# PDB Audit: Upgrade Impact Analysis

I'll analyze each PDB for upgrade safety. The key principle: **PDBs protect against disruption but can block necessary drain operations during upgrades**.

## ⚠️ **High Risk - Will Block Upgrades**

### Service A: `minAvailable=100%`
**Status:** 🚨 **WILL BLOCK UPGRADES**
- **Problem:** Requires ALL pods to remain available at all times
- **During upgrade:** When GKE tries to drain a node, it cannot evict any pods because that would drop availability below 100%
- **Fix:** Change to `minAvailable=50%` or `maxUnavailable=1` (assuming you have 2+ replicas)

### Service B: `maxUnavailable=0`
**Status:** 🚨 **WILL BLOCK UPGRADES** 
- **Problem:** Identical to 100% availability - no pods can ever be unavailable
- **During upgrade:** Node drain will fail because no pods can be evicted
- **Fix:** Allow at least 1 unavailable: `maxUnavailable=1`

## ✅ **Safe Configurations**

### Service C: `minAvailable=2` with 3 replicas
**Status:** ✅ **SAFE**
- **Analysis:** Allows 1 pod to be unavailable (3 total - 2 required = 1 drainable)
- **During upgrade:** GKE can evict 1 pod at a time while maintaining quorum
- **Recommendation:** Keep as-is - good balance of protection and upgradability

### Service D: `maxUnavailable=1` with 5 replicas
**Status:** ✅ **SAFE**
- **Analysis:** Permits 1 pod to be down, maintaining 4 available (80% uptime)
- **During upgrade:** Node drain can proceed by evicting 1 pod at a time
- **Recommendation:** Keep as-is - allows upgrades while protecting availability

## Recommended Fixes

```bash
# Service A: Fix the blocking PDB
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"50%","maxUnavailable":null}}'

# Service B: Allow some unavailability
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1}}'
```

## PDB Best Practices for Upgrades

### General Guidelines
- **Never use `minAvailable=100%` or `maxUnavailable=0`** - they always block drain
- **For N replicas, allow at least 1 unavailable** - enables pod-by-pod eviction
- **Use percentages for auto-scaling workloads** - `minAvailable=50%` adapts to replica changes

### Database-Specific Recommendations
```yaml
# 3-node database cluster (maintains quorum)
minAvailable: 2  # or maxUnavailable: 1

# MySQL primary-replica setup
minAvailable: 1  # keeps either primary or replica running

# Elasticsearch 3-master cluster
minAvailable: 2  # maintains quorum during upgrades
```

## Upgrade-Time Monitoring

Monitor PDB violations during upgrades:
```bash
# Check for PDB-blocked evictions in real time
kubectl get events -A --watch | grep -i pdb

# Cloud Logging query for PDB violations
resource.type="gke_cluster" jsonPayload.reason="EvictionBlocked"
```

GKE respects PDBs for **up to 1 hour**, then force-evicts. You'll get notifications for:
- `POD_PDB_VIOLATION` - eviction blocked by PDB
- `POD_NOT_ENOUGH_PDB` - insufficient replicas to satisfy PDB

## Summary

**Fix immediately:** Services A and B will block your upgrade
**Keep as-is:** Services C and D are safely configured

The goal is **balanced protection** - prevent cascading failures while allowing necessary maintenance operations. Your Services C and D demonstrate this balance perfectly.
# PDB Audit for GKE Upgrade Safety

I'll analyze each PDB configuration for upgrade safety. The key principle: **PDBs should protect against cascading failures while allowing controlled disruption during maintenance.**

## Current Configuration Analysis

| Service | Configuration | Replicas | Status | Risk Level |
|---------|--------------|----------|---------|------------|
| **Service A** | `minAvailable: 100%` | Unknown | ⚠️ **BLOCKS UPGRADES** | 🔴 HIGH |
| **Service B** | `maxUnavailable: 0` | Unknown | ⚠️ **BLOCKS UPGRADES** | 🔴 HIGH |  
| **Service C** | `minAvailable: 2` (3 replicas) | 3 | ✅ **SAFE** | 🟢 LOW |
| **Service D** | `maxUnavailable: 1` (5 replicas) | 5 | ✅ **SAFE** | 🟢 LOW |

## Detailed Analysis

### 🔴 Service A: `minAvailable: 100%` - WILL BLOCK UPGRADES
**Problem:** Requires ALL pods to remain available simultaneously. During node drain, GKE cannot evict ANY pod without violating the PDB.

**Impact:** Node drain will hang indefinitely. After 1 hour, GKE will force-evict pods anyway, but this defeats the PDB's purpose.

**Fix:**
```yaml
# Instead of minAvailable: 100%
spec:
  minAvailable: "80%"  # or minAvailable: N-1 where N is replica count
  # This allows 1-2 pods to be down while maintaining service
```

### 🔴 Service B: `maxUnavailable: 0` - WILL BLOCK UPGRADES  
**Problem:** Identical to 100% availability requirement. Zero pods can be unavailable = all pods must stay up.

**Fix:**
```yaml
# Instead of maxUnavailable: 0
spec:
  maxUnavailable: 1  # Allow 1 pod to be evicted during drain
```

### ✅ Service C: `minAvailable: 2` (3 replicas) - SAFE
**Analysis:** Allows 1 pod (33%) to be unavailable. During drain, 1 pod can be evicted while 2 remain serving.
- **Disruption budget:** 1 pod can be down
- **Upgrade behavior:** Node drain evicts 1 pod → remaining 2 continue serving → evicted pod reschedules to upgraded node

### ✅ Service D: `maxUnavailable: 1` (5 replicas) - SAFE  
**Analysis:** Explicitly allows 1 pod to be unavailable. During drain, 1 pod can be evicted while 4 remain serving.
- **Disruption budget:** 1 pod can be down  
- **Upgrade behavior:** Same as Service C - controlled, safe disruption

## Recommended PDB Strategy by Service Type

### Web Services / APIs (Stateless)
```yaml
spec:
  maxUnavailable: 25%  # Scales with replica count
  # 4 replicas = 1 can be down, 8 replicas = 2 can be down
```

### Databases / Stateful Services  
```yaml
spec:
  minAvailable: 2  # Maintain quorum for clustered databases
  # For 3-replica setup (common for Postgres, Elasticsearch masters)
```

### Background Workers
```yaml
spec:
  maxUnavailable: 50%  # More disruption-tolerant
  # Can handle multiple pods down simultaneously
```

### Single-Replica Services (avoid if possible)
```yaml
# No PDB - would block upgrades forever
# Instead: scale to 2+ replicas with PDB
spec:
  replicas: 2
  # Then add PDB with maxUnavailable: 1
```

## Immediate Action Items

1. **Fix Service A immediately:**
   ```bash
   kubectl patch pdb SERVICE-A-pdb -p '{"spec":{"minAvailable":"80%"}}'
   ```

2. **Fix Service B immediately:**  
   ```bash
   kubectl patch pdb SERVICE-B-pdb -p '{"spec":{"maxUnavailable":1}}'
   ```

3. **Test in staging:** Before your next upgrade, validate the new PDB settings don't break your availability requirements during normal operations.

## GKE Upgrade PDB Behavior

**Key facts for your upgrade planning:**
- **PDB timeout:** GKE respects PDBs for up to 1 hour during surge upgrades, then force-evicts
- **Monitoring:** GKE publishes PDB violation events to Cloud Logging (`POD_PDB_VIOLATION`, `POD_NOT_ENOUGH_PDB`)  
- **Blue-green upgrades:** Also respect PDBs during the drain phase, with same 1-hour timeout
- **Warning signs:** If you see upgrade operations taking >1 hour per node, PDBs are likely too restrictive

## Monitoring During Upgrades

Set up alerts for PDB violations:
```bash
# Check for PDB-blocked evictions in Cloud Logging
gcloud logging read 'resource.type="gke_cluster" 
  jsonPayload.reason="EvictionBlocked"' --limit=10

# Or monitor PDB status during upgrade
kubectl get pdb -A -w
```

Your **Service C and D are correctly configured** - they'll protect availability while allowing upgrades to proceed smoothly. **Service A and B will definitely block your upgrades** and should be fixed before your next maintenance window.
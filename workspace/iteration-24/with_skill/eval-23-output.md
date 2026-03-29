# PDB Audit for GKE Upgrade Safety

I'll analyze each PDB configuration for upgrade safety. The key principle: **GKE respects PDBs for up to 1 hour during node upgrades, then force-evicts remaining pods**. PDBs that are too restrictive will block drain and cause upgrade delays or failures.

## Current PDB Analysis

### ❌ **Service A: minAvailable=100% — BLOCKING**
**Risk:** Will block ALL node upgrades indefinitely
**Problem:** With 100% availability required, GKE can never evict pods from draining nodes
**Impact:** Node upgrades will stall for 1 hour, then force-evict (causing brief downtime anyway)

**Fix:**
```bash
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"90%"}}'
# Or if you have 3+ replicas:
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'
```

### ❌ **Service B: maxUnavailable=0 — BLOCKING**
**Risk:** Identical to 100% availability — will block upgrades
**Problem:** Zero unavailable pods means no pods can be evicted during drain
**Impact:** Same as Service A — 1-hour delay then force-eviction

**Fix:**
```bash
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1}}'
```

### ✅ **Service C: minAvailable=2 with 3 replicas — SAFE**
**Risk:** Low — allows 1 pod to be evicted
**Analysis:** 3 replicas - 2 required = 1 pod can be unavailable during drain
**Impact:** Upgrades proceed smoothly, maintains 67% capacity during node drain

**No changes needed** — this is well-configured.

### ✅ **Service D: maxUnavailable=1 with 5 replicas — SAFE**
**Risk:** Low — allows 1 pod eviction at a time
**Analysis:** Maintains 4/5 pods (80% capacity) during drain
**Impact:** Smooth upgrades with minimal capacity reduction

**No changes needed** — this is also well-configured.

## Recommended PDB Settings by Service Type

### Web Services / APIs (Stateless)
```yaml
# Allow 1 pod disruption OR 10% of replicas (whichever is higher)
spec:
  maxUnavailable: 1  # For small deployments (≤10 replicas)
  # OR
  maxUnavailable: 10%  # For larger deployments
```

### Databases / Stateful Services
```yaml
# Conservative — protect quorum but allow single-node drain
spec:
  minAvailable: 2  # For 3-node clusters (maintains quorum)
  # Examples:
  # - Elasticsearch 3-master: minAvailable=2
  # - MySQL replicas: minAvailable=1
  # - Cassandra: minAvailable=2 per DC
```

### Background Workers / Batch Processing
```yaml
# More permissive — can tolerate higher disruption
spec:
  maxUnavailable: 25%  # Allow quarter of workers to drain
```

## Immediate Actions Required

**Before your next upgrade:**

1. **Fix blocking PDBs immediately:**
```bash
# Service A - allow 1 disruption
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'

# Service B - allow 1 disruption  
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1}}'
```

2. **Test the changes:**
```bash
# Verify PDB allows disruptions
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS > 0 for all PDBs
```

3. **Monitor during upgrade:**
```bash
# Watch for PDB violations during upgrade
kubectl get events -A --field-selector reason=EvictionBlocked --watch
```

## Upgrade-Safe PDB Checklist

```markdown
PDB Upgrade Safety Checklist
- [ ] No PDB has minAvailable=100%
- [ ] No PDB has maxUnavailable=0  
- [ ] All PDBs show ALLOWED DISRUPTIONS > 0: `kubectl get pdb -A -o wide`
- [ ] Database PDBs preserve quorum (e.g., 2/3 masters available)
- [ ] Stateless service PDBs allow at least 1 pod eviction
- [ ] Large deployments (10+ replicas) use percentage-based disruptions
```

## Advanced: PDB Monitoring During Upgrades

Set up monitoring for PDB-blocked upgrades:

```bash
# Cloud Logging query for PDB violations
gcloud logging read 'resource.type="gke_cluster" 
  jsonPayload.reason="EvictionBlocked"
  jsonPayload.involvedObject.kind="Pod"' \
  --limit=10 --format="table(timestamp,jsonPayload.message)"
```

**Bottom line:** Services A and B will definitely block your upgrades. Fix those immediately. Services C and D are properly configured and safe for upgrades.
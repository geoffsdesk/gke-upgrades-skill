# PDB Audit for GKE Upgrade Safety

Based on your configuration, here's the safety assessment for each service during GKE upgrades:

## ❌ HIGH RISK - Will Block Upgrades

### Service A: `minAvailable=100%`
**Problem:** This completely blocks any pod eviction - GKE cannot drain nodes at all.
**Impact:** Node upgrade will stall indefinitely. GKE respects PDBs for 1 hour, then force-evicts.
**Fix:**
```yaml
# Change to allow 1 disruption
spec:
  maxUnavailable: 1
  # OR use percentage if you have many replicas
  maxUnavailable: "10%"
```

### Service B: `maxUnavailable=0`
**Problem:** Identical issue - zero disruptions allowed.
**Impact:** Same as Service A - will block drain completely.
**Fix:**
```yaml
# Allow minimal disruption
spec:
  maxUnavailable: 1
```

## ⚠️ MODERATE RISK - Context Dependent

### Service C: `minAvailable=2` with 3 replicas
**Status:** Allows 1 disruption (3-2=1) - **this is actually safe**
**During upgrade:** 1 pod can be evicted while 2 remain available
**Risk level:** Low - should not block upgrades under normal conditions
**Exception:** Could block if one replica is already unhealthy/crash-looping

## ✅ SAFE - Upgrade Friendly

### Service D: `maxUnavailable=1` with 5 replicas
**Status:** Perfect configuration - allows exactly 1 disruption
**During upgrade:** 1 pod evicted, 4 remain serving traffic
**Risk level:** Very low - ideal for rolling upgrades

## Recommended PDB Patterns

### For most services (3+ replicas):
```yaml
spec:
  maxUnavailable: 1  # Allow 1 pod to be disrupted
  selector:
    matchLabels:
      app: your-service
```

### For high-replica services (10+ pods):
```yaml
spec:
  maxUnavailable: "10%"  # Scale with replica count
  selector:
    matchLabels:
      app: your-service
```

### For databases/stateful workloads:
```yaml
spec:
  maxUnavailable: 1  # Conservative - one at a time
  selector:
    matchLabels:
      app: your-database
```

## Immediate Action Required

**Before your next upgrade:**

1. **Fix Service A and B immediately:**
```bash
# Service A
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":"10%"}}'

# Service B  
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1}}'
```

2. **Monitor Service C during upgrades:**
```bash
# Check if all replicas are healthy before upgrading
kubectl get pods -l app=service-c
# All should show Running/Ready
```

## Upgrade-Time Monitoring

Use these commands to watch for PDB issues during upgrades:

```bash
# Check PDB status during upgrade
kubectl get pdb -A -o wide

# Monitor upgrade events for PDB violations
kubectl get events -A --field-selector reason=EvictionBlocked --watch

# GKE disruption notifications (if configured)
gcloud logging read 'resource.type="gke_cluster" jsonPayload.reason="POD_PDB_VIOLATION"' --freshness=1h
```

## Key Insights

- **Service A & B will definitely block** your upgrades - fix these first priority
- **Service C is actually well-configured** despite seeming restrictive
- **Service D is the gold standard** - use this pattern for other services
- **PDB violations trigger force-eviction after 1 hour** - plan for this timeout

**Bottom line:** Fix Services A and B before your next upgrade window, and you should have smooth node drains. Service C and D are properly configured for GKE's rolling upgrade process.
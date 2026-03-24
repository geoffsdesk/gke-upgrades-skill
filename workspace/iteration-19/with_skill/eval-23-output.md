# PDB Configuration Audit for GKE Upgrades

## Critical Issues (Will Block Upgrades)

### ❌ Service A: `minAvailable=100%`
**Risk Level: HIGH - Will definitely block upgrades**

This configuration prevents ANY pod from being evicted, making node drain impossible during upgrades.

**Why it blocks:** GKE needs to drain nodes during upgrades, but `minAvailable=100%` means zero pods can be disrupted simultaneously.

**Recommended fix:**
```bash
# Option 1: Allow some disruption
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"90%","maxUnavailable":null}}'

# Option 2: Use absolute count if you know replica count
# For 10 replicas, allow 1 to be down:
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":9,"maxUnavailable":null}}'
```

### ❌ Service B: `maxUnavailable=0`
**Risk Level: HIGH - Will definitely block upgrades**

Same effect as `minAvailable=100%` - prevents any pod eviction.

**Recommended fix:**
```bash
# Allow at least 1 pod disruption
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1,"minAvailable":null}}'

# Or use percentage for better scaling
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"10%","minAvailable":null}}'
```

## Safe Configurations

### ✅ Service C: `minAvailable=2` with 3 replicas
**Risk Level: LOW - Safe for upgrades**

This allows 1 pod disruption (3-2=1), which enables node drain to proceed. Good configuration for maintaining service availability during upgrades.

### ✅ Service D: `maxUnavailable=1` with 5 replicas
**Risk Level: LOW - Safe for upgrades**

This allows 1 pod disruption while keeping 4 pods running. Well-balanced for both availability and upgrade flexibility.

## Recommended PDB Best Practices

### General Guidelines

1. **Always allow at least 1 pod disruption** - Never use `minAvailable=100%` or `maxUnavailable=0`
2. **Use percentages for dynamic scaling** - Better than absolute counts for services that autoscale
3. **Consider your minimum viable capacity** - What's the minimum pods needed to serve traffic?

### Recommended Patterns by Service Type

```yaml
# Web services (stateless)
apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  minAvailable: 75%  # Or maxUnavailable: 25%
  selector:
    matchLabels:
      app: web-service

# Databases (stateful, require quorum)
apiVersion: policy/v1
kind: PodDisruptionBudget  
spec:
  minAvailable: 2  # For 3-node cluster, maintains quorum
  selector:
    matchLabels:
      app: database

# Background workers (can tolerate more disruption)
apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  maxUnavailable: 50%  # Can lose half the workers temporarily
  selector:
    matchLabels:
      app: worker
```

## Upgrade-Safe Configuration Changes

### Service A & B (Critical Fixes)
```bash
# Backup current configs first
kubectl get pdb service-a-pdb -o yaml > service-a-pdb-backup.yaml
kubectl get pdb service-b-pdb -o yaml > service-b-pdb-backup.yaml

# Apply safer configs
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"90%","maxUnavailable":null}}'
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"10%","minAvailable":null}}'
```

### Test PDB Changes
```bash
# Verify new settings
kubectl get pdb -o custom-columns=NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,ALLOWED-DISRUPTIONS:.status.disruptionsAllowed

# Ensure ALLOWED-DISRUPTIONS > 0 for all PDBs
```

## GKE Upgrade Behavior with PDBs

**Important Context:**
- GKE respects PDBs for up to **1 hour** during surge upgrades
- After 1 hour, pods are **force-evicted** even if PDB would be violated
- You can monitor PDB violations in Cloud Logging: `resource.type="gke_cluster" jsonPayload.reason="EvictionBlocked"`

**Surge vs Blue-Green Implications:**
- **Surge upgrades**: PDB violations delay drain for max 1 hour, then force-proceed
- **Blue-green upgrades**: More time for graceful drain respecting PDBs during soak period
- **Autoscaled blue-green**: Best for long graceful termination periods

## Monitoring During Upgrades

Set up alerts for PDB violations:
```bash
# Check PDB status during upgrade
kubectl get pdb -A -o wide

# Monitor events for eviction blocks
kubectl get events -A --field-selector reason=EvictionBlocked

# GKE disruption notifications in Cloud Logging
gcloud logging read 'resource.type="gke_cluster" jsonPayload.reason="POD_PDB_VIOLATION"' --limit=10
```

## Summary & Next Steps

1. **Immediate action required**: Fix Service A and Service B PDBs - they will block upgrades
2. **Service C and D are safe** - no changes needed
3. **Test the fixes** in a dev/staging environment first
4. **Monitor PDB status** during your next upgrade to validate the changes work

Your Services C and D show good PDB practices. Apply similar patterns to Services A and B to maintain availability while allowing upgrades to proceed smoothly.
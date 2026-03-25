# PDB Upgrade Risk Audit

I'll analyze each of your PDB configurations for upgrade safety. The key insight is that **overly restrictive PDBs will block node drain during upgrades**, causing the upgrade to stall.

## Your PDB Analysis

| Service | Current PDB | Risk Level | Upgrade Impact | Recommendation |
|---------|-------------|------------|----------------|----------------|
| **Service A** | `minAvailable=100%` | 🚨 **CRITICAL** | **BLOCKS ALL UPGRADES** | Change to `maxUnavailable=1` or `minAvailable=N-1` |
| **Service B** | `maxUnavailable=0` | 🚨 **CRITICAL** | **BLOCKS ALL UPGRADES** | Change to `maxUnavailable=1` |
| **Service C** | `minAvailable=2` (3 replicas) | 🚨 **HIGH RISK** | **LIKELY TO BLOCK** | Change to `minAvailable=1` or `maxUnavailable=1` |
| **Service D** | `maxUnavailable=1` (5 replicas) | ✅ **SAFE** | No issues expected | Keep current setting |

## Detailed Assessment

### Service A: minAvailable=100% 🚨
**Problem:** This guarantees ALL pods must stay running, making it impossible to drain any node with Service A pods.

**Fix:**
```yaml
spec:
  maxUnavailable: 1  # Allow 1 pod to be evicted during upgrade
  # OR
  minAvailable: "N-1"  # Keep all but 1 pod running
```

### Service B: maxUnavailable=0 🚨
**Problem:** Identical to 100% minAvailable - no pods can ever be disrupted.

**Fix:**
```yaml
spec:
  maxUnavailable: 1  # Allow 1 pod disruption
```

### Service C: minAvailable=2 with 3 replicas 🚨
**Problem:** Only allows 1 pod disruption, but if 2 pods happen to land on the same node being drained, the PDB blocks eviction.

**Risk scenario:** Node has 2 of your 3 replicas → drain attempts to evict both → PDB violation → upgrade stalls.

**Fix options:**
```yaml
# Option 1: More forgiving
spec:
  minAvailable: 1  # Guarantees service availability, allows more flexibility

# Option 2: Explicit disruption limit
spec:
  maxUnavailable: 1  # Clear about disruption tolerance
```

### Service D: maxUnavailable=1 with 5 replicas ✅
**Perfect:** Allows 1 pod disruption while keeping 4 running. This handles most upgrade scenarios safely.

## Upgrade-Safe PDB Recommendations

### For stateless services (web apps, APIs):
```yaml
spec:
  maxUnavailable: 1  # Allow 1 pod eviction, keeps service running
```

### For databases/stateful services:
```yaml
spec:
  maxUnavailable: 1        # Conservative - only 1 replica down at a time
  # AND ensure proper anti-affinity to spread pods across nodes
```

### For high-replica services (10+ pods):
```yaml
spec:
  maxUnavailable: "10%"    # Percentage-based for better scaling
```

## Pod Anti-Affinity Check

Your PDBs won't help if pods cluster on the same nodes. Verify you have anti-affinity rules:

```bash
# Check current pod distribution
kubectl get pods -o wide -l app=SERVICE_NAME

# Example anti-affinity (add to your deployments):
```
```yaml
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: SERVICE_NAME
              topologyKey: kubernetes.io/hostname
```

## Testing Your PDBs

Before your upgrade, simulate node drain to test PDB behavior:

```bash
# Pick a node with your service pods
kubectl get pods -o wide -l app=SERVICE_NAME

# Simulate drain (don't actually drain yet)
kubectl drain NODE_NAME --dry-run=client --ignore-daemonsets

# If this fails with PDB violations, your PDBs are too restrictive
```

## Immediate Action Plan

**Before your next upgrade:**

1. **Fix Service A & B immediately** - they WILL block your upgrade
2. **Adjust Service C** to `minAvailable=1` or `maxUnavailable=1` 
3. **Keep Service D** as-is - it's well configured
4. **Test the changes** with the drain simulation above
5. **Verify anti-affinity** rules spread pods across nodes

## Monitoring During Upgrade

Watch for PDB-related upgrade blocks:

```bash
# Monitor PDB status during upgrade
kubectl get pdb -A -w

# Check for disruption events
kubectl get events -A --field-selector reason=EvictionBlocked
```

GKE will respect your PDBs for up to 1 hour during node drain, then force-evict if necessary. You'll see warnings in Cloud Logging before force-eviction occurs.

**Bottom line:** Services A and B will definitely block your upgrade. Service C is risky depending on pod placement. Fix these before your maintenance window to avoid a stalled upgrade.